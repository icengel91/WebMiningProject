"""X/Twitter crawler — discover viral tweets and track engagement over time.

Uses **Playwright** (headless Chromium) to scrape X search results, since
the unofficial API libraries (twscrape, twikit) are frequently broken by
X's anti-bot changes.  Price windows around each tweet are fetched via
``yfinance``.
"""

import asyncio
import json
import logging
import random
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pandas as pd
import yfinance as yf
from playwright.async_api import BrowserContext, Page, async_playwright

from src.scraping import x_config as cfg
from src.scraping.db import (
    get_db,
    store_price_snapshot,
    store_snapshot,
    store_tweet,
)

logger = logging.getLogger(__name__)

# Regex to extract cashtags like $TSLA, $AAPL from tweet text
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


@dataclass
class ScrapedTweet:
    """Lightweight container for data extracted from one tweet article."""

    tweet_id: str
    author: str
    author_followers: int
    content: str
    posted_at: str        # ISO 8601
    likes: int
    retweets: int


def extract_cashtag(text: str) -> str | None:
    """Return the first cashtag symbol found in *text*, or None."""
    match = _CASHTAG_RE.search(text)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Playwright browser helpers
# ---------------------------------------------------------------------------

async def _launch_browser_context() -> tuple:
    """Launch headless Chromium and return (playwright, browser, context).

    Cookies from TWSCRAPE_ACCOUNTS env var are injected so that X
    recognises the session.
    """
    pw = await async_playwright().start()
    launch_kwargs: dict = {"headless": True}
    if cfg.CHROMIUM_EXECUTABLE:
        launch_kwargs["executable_path"] = cfg.CHROMIUM_EXECUTABLE
        logger.info("Using custom Chromium: %s", cfg.CHROMIUM_EXECUTABLE)
    browser = await pw.chromium.launch(**launch_kwargs)
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )

    # Inject cookies from config
    accounts = cfg.get_twscrape_accounts()
    if not accounts:
        raise RuntimeError(
            "No accounts configured. "
            "Set TWSCRAPE_ACCOUNTS in configs/.env — see configs/.env.example"
        )
    cookies_str = accounts[0].get("cookies", "")
    if not cookies_str:
        raise RuntimeError(
            "No cookies found in TWSCRAPE_ACCOUNTS. "
            "Provide ct0 and auth_token — see configs/.env.example"
        )
    cookie_list = []
    for pair in cookies_str.split(";"):
        k, _, v = pair.strip().partition("=")
        if k and v:
            cookie_list.append(
                {"name": k, "value": v, "domain": ".x.com", "path": "/"}
            )
    await ctx.add_cookies(cookie_list)
    logger.info("Browser context ready with %d cookies.", len(cookie_list))
    return pw, browser, ctx


def _parse_stat(raw: str) -> int:
    """Convert a stat string like '1.2K' or '530' to an integer."""
    raw = raw.strip().replace(",", "")
    if not raw:
        return 0
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if raw.upper().endswith(suffix):
            return int(float(raw[:-1]) * mult)
    try:
        return int(raw)
    except ValueError:
        return 0


async def _scrape_search_page(
    page: Page,
    query: str,
    limit: int,
) -> list[ScrapedTweet]:
    """Navigate to X search and extract tweets from the page.

    Scrolls down to collect up to *limit* tweets.
    """
    encoded_q = quote(query)
    url = f"https://x.com/search?q={encoded_q}&src=typed_query&f=live"
    logger.info("Navigating to %s", url)

    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

    try:
        await page.wait_for_selector(
            'article[data-testid="tweet"]', timeout=20_000,
        )
    except Exception:
        logger.warning("No tweets loaded for query '%s'.", query)
        return []

    collected: dict[str, ScrapedTweet] = {}
    max_scrolls = max(limit // 3, 5)

    for _ in range(max_scrolls):
        if len(collected) >= limit:
            break

        articles = await page.query_selector_all('article[data-testid="tweet"]')
        for article in articles:
            if len(collected) >= limit:
                break
            try:
                tweet = await _parse_article(article)
                if tweet and tweet.tweet_id not in collected:
                    collected[tweet.tweet_id] = tweet
            except Exception:
                logger.debug("Skipping unparseable article.", exc_info=True)

        # Scroll down for more tweets
        await page.evaluate("window.scrollBy(0, 800)")
        await asyncio.sleep(random.uniform(cfg.REQUEST_DELAY_MIN, cfg.REQUEST_DELAY_MAX))

    logger.info("Scraped %d tweets for query '%s'.", len(collected), query)
    return list(collected.values())


async def _parse_article(article) -> ScrapedTweet | None:
    """Extract structured data from a single tweet <article> element."""
    # Tweet text
    text_el = await article.query_selector('div[data-testid="tweetText"]')
    content = await text_el.inner_text() if text_el else ""

    # Author handle from the link href (e.g. "/elonmusk")
    user_link = await article.query_selector('div[data-testid="User-Name"] a')
    if not user_link:
        return None
    href = await user_link.get_attribute("href") or ""
    author = href.strip("/").split("/")[0] if href else ""
    if not author:
        return None

    # Tweet ID from the status link (e.g. "/user/status/123456")
    time_link = await article.query_selector("a time")
    if time_link is None:
        # Try alternative: find <time> element directly
        time_el = await article.query_selector("time")
        if time_el is None:
            return None
        parent_a = await time_el.evaluate_handle("el => el.closest('a')")
        status_href = await parent_a.get_attribute("href") if parent_a else ""
    else:
        parent_a = await time_link.evaluate_handle("el => el.closest('a')")
        status_href = await parent_a.get_attribute("href") if parent_a else ""

    # Extract tweet ID from "/user/status/123456"
    tweet_id = ""
    if status_href:
        parts = status_href.strip("/").split("/")
        for i, part in enumerate(parts):
            if part == "status" and i + 1 < len(parts):
                tweet_id = parts[i + 1]
                break
    if not tweet_id:
        return None

    # Posted time
    time_el = await article.query_selector("time")
    posted_at = ""
    if time_el:
        posted_at = await time_el.get_attribute("datetime") or ""

    # Engagement stats
    likes = 0
    retweets = 0
    like_el = await article.query_selector('button[data-testid="like"] span')
    if like_el:
        likes = _parse_stat(await like_el.inner_text())
    rt_el = await article.query_selector('button[data-testid="retweet"] span')
    if rt_el:
        retweets = _parse_stat(await rt_el.inner_text())

    return ScrapedTweet(
        tweet_id=tweet_id,
        author=author,
        author_followers=0,  # not visible on search results page
        content=content,
        posted_at=posted_at or datetime.now(timezone.utc).isoformat(),
        likes=likes,
        retweets=retweets,
    )


async def _get_follower_count(page: Page, username: str) -> int:
    """Visit a user's profile page and extract their follower count."""
    try:
        await page.goto(
            f"https://x.com/{username}",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await page.wait_for_selector(
            'a[href$="/verified_followers"]', timeout=10_000,
        )
        followers_link = await page.query_selector('a[href$="/verified_followers"]')
        if not followers_link:
            followers_link = await page.query_selector('a[href$="/followers"]')
        if followers_link:
            text = await followers_link.inner_text()
            # e.g. "215.8M Followers" or "1,234 Followers"
            num_part = text.split()[0] if text else "0"
            return _parse_stat(num_part)
    except Exception:
        logger.debug("Could not fetch followers for @%s", username, exc_info=True)
    return 0


# ---------------------------------------------------------------------------
# Core crawler functions
# ---------------------------------------------------------------------------

async def discover_tweets(
    ctx: BrowserContext,
    conn: sqlite3.Connection,
    queries: list[str] | None = None,
    limit: int | None = None,
) -> int:
    """Search X for stock-related tweets and store new ones.

    Args:
        ctx: Playwright browser context with X cookies.
        conn: SQLite connection.
        queries: Override search queries (defaults to ``x_config.QUERIES``).
        limit: Max tweets per query (defaults to ``x_config.DISCOVERY_LIMIT``).

    Returns:
        Number of newly stored tweets.
    """
    queries = queries or cfg.QUERIES
    limit = limit or cfg.DISCOVERY_LIMIT
    new_count = 0

    page = await ctx.new_page()

    for query in queries:
        # Inject min_faves filter into the query so X pre-filters server-side.
        # This reduces the number of scraped tweets that need follower lookup.
        effective_query = query
        if cfg.MIN_LIKES > 0:
            effective_query = f"{query} min_faves:{cfg.MIN_LIKES}"
        scraped = await _scrape_search_page(page, effective_query, limit)

        for tweet in scraped:
            symbol = extract_cashtag(tweet.content)

            # Filter by like count FIRST — no extra request needed.
            # This avoids visiting profile pages for low-engagement tweets,
            # which is the main trigger for X's bot detection.
            if tweet.likes < cfg.MIN_LIKES:
                logger.debug(
                    "Skipping tweet %s (%d likes < %d threshold).",
                    tweet.tweet_id, tweet.likes, cfg.MIN_LIKES,
                )
                continue

            # Fetch follower count only for tweets that passed the like filter
            if tweet.author_followers == 0:
                tweet.author_followers = await _get_follower_count(page, tweet.author)
                await asyncio.sleep(random.uniform(0.5, 1.0))

            # Filter by follower count
            if tweet.author_followers < cfg.MIN_FOLLOWERS:
                logger.debug(
                    "Skipping @%s (%d followers < %d threshold).",
                    tweet.author, tweet.author_followers, cfg.MIN_FOLLOWERS,
                )
                continue

            inserted = store_tweet(
                conn,
                tweet_id=tweet.tweet_id,
                author=tweet.author,
                author_followers=tweet.author_followers,
                content=tweet.content,
                posted_at=tweet.posted_at,
                symbol=symbol,
            )
            if inserted:
                new_count += 1
                logger.info(
                    "New tweet %s by @%s (%d followers) — %s",
                    tweet.tweet_id,
                    tweet.author,
                    tweet.author_followers,
                    symbol or "no cashtag",
                )
                # First engagement snapshot
                store_snapshot(
                    conn,
                    tweet_id=tweet.tweet_id,
                    likes=tweet.likes,
                    retweets=tweet.retweets,
                )
                # Fetch price window if a symbol was detected
                if symbol:
                    posted_dt = datetime.fromisoformat(tweet.posted_at)
                    await _fetch_price_window(conn, tweet.tweet_id, symbol, posted_dt)

    await page.close()
    logger.info("Discovery complete — %d new tweets stored.", new_count)
    return new_count


async def _fetch_price_window(
    conn: sqlite3.Connection,
    tweet_id: str,
    symbol: str,
    tweet_time: datetime,
) -> None:
    """Download minute-level price data around *tweet_time* and store it."""
    start = tweet_time - timedelta(minutes=cfg.PRICE_OFFSET_BEFORE_MINUTES)
    end = tweet_time + timedelta(minutes=cfg.PRICE_OFFSET_AFTER_MINUTES)

    logger.info(
        "Fetching %s prices [%s → %s] for tweet %s",
        symbol, start.isoformat(), end.isoformat(), tweet_id,
    )
    try:
        data = yf.download(
            symbol,
            start=start,
            end=end,
            interval="1m",
            progress=False,
            auto_adjust=True,
        )
        if data.empty:
            # Check whether the window overlaps with NYSE trading hours
            # (Mon–Fri 14:30–21:00 UTC). If not, markets were simply closed.
            def _is_trading_window(dt: datetime) -> bool:
                """Return True if *dt* falls on a weekday within NYSE hours."""
                # Ensure UTC
                utc = dt.astimezone(timezone.utc)
                if utc.weekday() >= 5:  # Saturday=5, Sunday=6
                    return False
                open_h, close_h = 14, 21   # 09:30–16:00 ET → ~14:30–21:00 UTC
                return open_h <= utc.hour < close_h

            if not _is_trading_window(start) and not _is_trading_window(end):
                logger.info(
                    "No price data for %s — markets were closed during this window "
                    "(%s UTC, %s).",
                    symbol,
                    start.strftime("%Y-%m-%d %H:%M"),
                    "weekend" if start.astimezone(timezone.utc).weekday() >= 5
                    else "outside trading hours (NYSE 09:30–16:00 ET)",
                )
            else:
                logger.warning(
                    "No price data for %s in window — symbol may be delisted "
                    "or yfinance rate-limited.",
                    symbol,
                )
            return

        # Flatten MultiIndex columns produced by newer yfinance versions
        # e.g. ("Close", "TSLA") → "Close"
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        for ts, row in data.iterrows():
            store_price_snapshot(
                conn,
                tweet_id=tweet_id,
                symbol=symbol,
                timestamp=ts.isoformat(),
                price=float(row["Close"]),
                volume=int(row["Volume"]),
            )
        logger.info("Stored %d price rows for tweet %s.", len(data), tweet_id)

    except Exception:
        logger.exception("Failed to fetch prices for %s", symbol)


async def poll_tracked_tweets(ctx: BrowserContext, conn: sqlite3.Connection) -> int:
    """Re-crawl engagement metrics for tweets still within the polling window.

    Opens each tweet's page to read current likes/retweets.

    Returns:
        Number of snapshots created.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cfg.POLL_DURATION_MINUTES)
    cursor = conn.execute(
        "SELECT tweet_id, author, posted_at FROM tweets WHERE posted_at > ?",
        (cutoff.isoformat(),),
    )
    rows = cursor.fetchall()
    if not rows:
        logger.info("No tweets within polling window.")
        return 0

    page = await ctx.new_page()
    snapshot_count = 0

    for tweet_id, author, _ in rows:
        try:
            url = f"https://x.com/{author}/status/{tweet_id}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_selector(
                'article[data-testid="tweet"]', timeout=10_000,
            )
            article = await page.query_selector('article[data-testid="tweet"]')
            if article is None:
                logger.warning("Tweet %s not found on page.", tweet_id)
                continue

            likes = 0
            retweets = 0
            like_el = await article.query_selector('button[data-testid="like"] span')
            if like_el:
                likes = _parse_stat(await like_el.inner_text())
            rt_el = await article.query_selector('button[data-testid="retweet"] span')
            if rt_el:
                retweets = _parse_stat(await rt_el.inner_text())

            store_snapshot(conn, tweet_id, likes, retweets)
            snapshot_count += 1
            logger.debug(
                "Snapshot for %s: %d likes, %d RTs",
                tweet_id, likes, retweets,
            )
        except Exception:
            logger.exception("Error polling tweet %s", tweet_id)

        await asyncio.sleep(random.uniform(cfg.REQUEST_DELAY_MIN, cfg.REQUEST_DELAY_MAX))

    await page.close()
    logger.info("Polling complete — %d snapshots stored.", snapshot_count)
    return snapshot_count


async def run(
    queries: list[str] | None = None,
    limit: int | None = None,
) -> None:
    """Main entry point: discover tweets, then poll until the window closes."""
    conn = get_db()
    pw, browser, ctx = await _launch_browser_context()

    try:
        # --- Discovery pass ---
        await discover_tweets(ctx, conn, queries=queries, limit=limit)

        # --- Polling loop ---
        logger.info(
            "Starting polling loop (every %d min, for %d min window).",
            cfg.POLL_INTERVAL_MINUTES,
            cfg.POLL_DURATION_MINUTES,
        )
        end_time = datetime.now(timezone.utc) + timedelta(minutes=cfg.POLL_DURATION_MINUTES)

        while datetime.now(timezone.utc) < end_time:
            await poll_tracked_tweets(ctx, conn)
            logger.info("Sleeping %d minutes until next poll…", cfg.POLL_INTERVAL_MINUTES)
            await asyncio.sleep(cfg.POLL_INTERVAL_MINUTES * 60)

        # Final poll
        await poll_tracked_tweets(ctx, conn)
    finally:
        await browser.close()
        await pw.stop()
        conn.close()
        logger.info("Crawler finished.")
