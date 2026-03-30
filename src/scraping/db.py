"""SQLite database helpers for the X/Twitter crawler.

Manages the ``webmining.db`` file with three tables:
- ``tweets`` – one row per discovered tweet
- ``tweet_snapshots`` – engagement metrics re-crawled over time
- ``price_snapshots`` – minute-level prices around each tweet
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = _PROJECT_ROOT / "data" / "webmining.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tweets (
    tweet_id         TEXT PRIMARY KEY,
    author           TEXT NOT NULL,
    author_followers INTEGER,
    content          TEXT,
    posted_at        TEXT NOT NULL,
    symbol           TEXT
);

CREATE TABLE IF NOT EXISTS tweet_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id    TEXT NOT NULL REFERENCES tweets(tweet_id),
    crawled_at  TEXT NOT NULL,
    likes       INTEGER,
    retweets    INTEGER
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id    TEXT NOT NULL REFERENCES tweets(tweet_id),
    symbol      TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    price       REAL,
    volume      INTEGER
);
"""


def get_db(path: Path | None = None) -> sqlite3.Connection:
    """Return a connection to the SQLite database, creating tables if needed.

    Args:
        path: Override database file location (useful for tests).
    """
    db_path = path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    logger.info("Database ready at %s", db_path)
    return conn


def store_tweet(
    conn: sqlite3.Connection,
    tweet_id: str,
    author: str,
    author_followers: int,
    content: str,
    posted_at: str,
    symbol: str | None,
) -> bool:
    """Insert a tweet row. Returns True if inserted, False if duplicate."""
    try:
        conn.execute(
            "INSERT INTO tweets (tweet_id, author, author_followers, content, posted_at, symbol) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tweet_id, author, author_followers, content, posted_at, symbol),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        logger.debug("Tweet %s already stored, skipping.", tweet_id)
        return False


def store_snapshot(
    conn: sqlite3.Connection,
    tweet_id: str,
    likes: int,
    retweets: int,
) -> None:
    """Insert an engagement snapshot for a tracked tweet."""
    conn.execute(
        "INSERT INTO tweet_snapshots (tweet_id, crawled_at, likes, retweets) "
        "VALUES (?, ?, ?, ?)",
        (tweet_id, datetime.now(timezone.utc).isoformat(), likes, retweets),
    )
    conn.commit()


def store_price_snapshot(
    conn: sqlite3.Connection,
    tweet_id: str,
    symbol: str,
    timestamp: str,
    price: float,
    volume: int,
) -> None:
    """Insert a single price data point linked to a tweet."""
    conn.execute(
        "INSERT INTO price_snapshots (tweet_id, symbol, timestamp, price, volume) "
        "VALUES (?, ?, ?, ?, ?)",
        (tweet_id, symbol, timestamp, price, volume),
    )
    conn.commit()


def get_tracked_tweet_ids(conn: sqlite3.Connection) -> list[str]:
    """Return tweet IDs that are still within the polling window."""
    cursor = conn.execute("SELECT tweet_id FROM tweets")
    return [row[0] for row in cursor.fetchall()]
