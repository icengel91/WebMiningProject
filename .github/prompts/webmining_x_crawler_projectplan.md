# Web Mining – X Crawler for Stock Market Sentiment

## Research Goal

Investigating the influence of viral social media posts on stock prices.
**Core question:** Can viral posts on X (Twitter) trigger measurable price changes?

---

## Methodological Design

### What is measured

| Data Point | Description |
|---|---|
| Tweets | Filtered by trading hashtags & cashtags |
| Engagement growth | Likes/Retweets over time (polling loop) |
| Virality factor | Account size (followers) as a weighting factor |
| Stock prices | Time window **before and after** the tweet |

### Important Methodological Note

The causality problem must be addressed in the written report:
Price changes following a viral post may have **confounding variables**
(e.g. simultaneous company news, broader market trends). Phrasing: *"Correlation, not
necessarily causation"*.

---

## Crawler Architecture

### Technology Stack

- **`twscrape`** – uses X's internal web API (no paid API subscription needed)
- **`yfinance`** – stock price data at minute-level granularity
- **`sqlite3`** – local data storage
- **`asyncio`** – asynchronous polling loop

```bash
pip install twscrape yfinance
```

### Search Strategy

```python
QUERIES = [
    "$TSLA lang:en",
    "$AAPL lang:en",
    "$SAP lang:de OR lang:en",
    "#stockmarket lang:en",
    "#trading lang:en",
    "#daytrading lang:en",
    "#aktien lang:de",
]

# Celebrity filter (Option A: fixed list of known accounts)
KNOWN_ACCOUNTS = ["elonmusk", "chamath", "jimcramer"]

# Or dynamically (Option B: follower threshold)
MIN_FOLLOWERS = 100_000
```

---

## Database Schema

```sql
-- Core table: one entry per discovered tweet
CREATE TABLE tweets (
    tweet_id         TEXT PRIMARY KEY,
    author           TEXT,
    author_followers INTEGER,
    content          TEXT,
    posted_at        TEXT,   -- ISO 8601 timestamp
    symbol           TEXT    -- e.g. "$TSLA"
);

-- Polling table: crawled multiple times over time
-- → allows reconstruction of the engagement growth curve
CREATE TABLE tweet_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id    TEXT REFERENCES tweets(tweet_id),
    crawled_at  TEXT,   -- timestamp of this snapshot
    likes       INTEGER,
    retweets    INTEGER
);

-- Price table: time window around the tweet
-- → offset before and after posted_at
CREATE TABLE price_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id    TEXT REFERENCES tweets(tweet_id),
    symbol      TEXT,
    timestamp   TEXT,
    price       REAL,
    volume      INTEGER
);
```

---

## Crawler Logic (Skeleton)

```python
import asyncio
import sqlite3
from datetime import datetime, timedelta
from twscrape import API
import yfinance as yf

# --- Configuration ---
POLL_INTERVAL_MINUTES = 15      # How often a tweet is re-crawled
POLL_DURATION_MINUTES = 120     # How long a tweet is tracked
PRICE_OFFSET_BEFORE   = 30      # Minutes before the tweet
PRICE_OFFSET_AFTER    = 120     # Minutes after the tweet

# --- Initialize database ---
conn = sqlite3.connect("webmining.db")
# (INSERT CREATE TABLE statements here)

# --- Discover new tweets ---
async def discover_tweets(api, query, limit=500):
    async for tweet in api.search(query, limit=limit):
        # Filter: known accounts OR minimum follower threshold
        if tweet.user.followersCount < MIN_FOLLOWERS:
            continue
        store_tweet(tweet, query)
        await fetch_price_window(tweet)

# --- Save a snapshot of a tweet ---
def store_snapshot(tweet_id, likes, retweets):
    conn.execute(
        "INSERT INTO tweet_snapshots VALUES (NULL,?,?,?,?)",
        (tweet_id, datetime.utcnow().isoformat(), likes, retweets)
    )
    conn.commit()

# --- Fetch price time window ---
async def fetch_price_window(tweet):
    symbol = extract_cashtag(tweet.rawContent)  # e.g. "$TSLA" → "TSLA"
    if not symbol:
        return
    start = tweet.date - timedelta(minutes=PRICE_OFFSET_BEFORE)
    end   = tweet.date + timedelta(minutes=PRICE_OFFSET_AFTER)
    data  = yf.download(symbol, start=start, end=end, interval="1m")
    for ts, row in data.iterrows():
        conn.execute(
            "INSERT INTO price_snapshots VALUES (NULL,?,?,?,?,?)",
            (str(tweet.id), symbol, ts.isoformat(), row["Close"], row["Volume"])
        )
    conn.commit()

# --- Polling loop ---
async def polling_loop():
    # Track known tweets for POLL_DURATION_MINUTES
    # Every POLL_INTERVAL_MINUTES → save a new snapshot
    pass
```

---

## Rate Limiting & Anti-Ban Measures

```python
import time, random

# Wait between requests
time.sleep(random.uniform(1.5, 3.0))

# Use multiple accounts in a pool (recommended: 2–3 throwaway accounts)
await api.pool.add_account("user1", "pass1", "email1", "emailpass1")
await api.pool.add_account("user2", "pass2", "email2", "emailpass2")
await api.pool.login_all()
```

---

## Written Report – Documentation Checklist

| Chapter | Content |
|---|---|
| **Search strategy** | Choice of queries and justification |
| **Virality definition** | How is "viral" operationalized? (growth rate, absolute count, follower weighting) |
| **Time window choice** | Why -30/+120 minutes? Reasoning |
| **Confounding** | Why correlation ≠ causation (name confounding variables) |
| **Ethics & legal** | Reflect on ToS implications of using twscrape |
| **Data volume** | Number of tweets, time period, symbols covered |
| **Data quality** | Duplicates, bots, spam – how are they filtered? |

---

## Recommended Project Structure

```
webmining-x-crawler/
├── crawler/
│   ├── discover.py      # Find new tweets
│   ├── poll.py          # Track known tweets over time
│   └── prices.py        # Fetch stock price data
├── data/
│   └── webmining.db     # SQLite database
├── analysis/
│   └── correlation.py   # Analysis for the written report
├── config.py            # Queries, thresholds, offsets
└── main.py              # Entry point
```
