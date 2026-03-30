"""CLI entry point for the X/Twitter crawler.

Usage:
    python -m src.scraping.main                        # full run with defaults
    python -m src.scraping.main --discover-only        # discover tweets, skip polling
    python -m src.scraping.main --limit 50             # cap tweets per query
    python -m src.scraping.main --queries '$TSLA lang:en' '#crypto lang:en'
"""

import argparse
import asyncio
import logging
import sys

from src.scraping import x_crawler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X/Twitter crawler for stock-market sentiment analysis.",
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        default=None,
        help="Override search queries (default: from x_config.py).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max tweets to fetch per query (default: 500).",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Run discovery pass only — skip the polling loop.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    if args.discover_only:
        from src.scraping.db import get_db

        async def _discover() -> None:
            conn = get_db()
            pw, browser, ctx = await x_crawler._launch_browser_context()
            try:
                await x_crawler.discover_tweets(
                    ctx, conn, queries=args.queries, limit=args.limit,
                )
            finally:
                await browser.close()
                await pw.stop()
                conn.close()

        asyncio.run(_discover())
    else:
        asyncio.run(x_crawler.run(queries=args.queries, limit=args.limit))


if __name__ == "__main__":
    main()
