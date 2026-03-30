"""Tests for the SQLite database helpers."""

import sqlite3

import pytest

from src.scraping.db import (
    get_db,
    get_tracked_tweet_ids,
    store_price_snapshot,
    store_snapshot,
    store_tweet,
)


@pytest.fixture()
def conn(tmp_path):
    """Provide a fresh in-memory-like DB for each test."""
    db_path = tmp_path / "test.db"
    return get_db(db_path)


class TestGetDb:
    def test_creates_tables(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {t[0] for t in tables}
        assert {"tweets", "tweet_snapshots", "price_snapshots"}.issubset(names)

    def test_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn1 = get_db(db_path)
        conn2 = get_db(db_path)  # should not raise
        conn1.close()
        conn2.close()


class TestStoreTweet:
    def test_insert_new(self, conn):
        ok = store_tweet(conn, "1", "alice", 500_000, "Buy $TSLA", "2026-01-01T12:00:00", "TSLA")
        assert ok is True
        row = conn.execute("SELECT * FROM tweets WHERE tweet_id='1'").fetchone()
        assert row is not None
        assert row[1] == "alice"

    def test_duplicate_returns_false(self, conn):
        store_tweet(conn, "1", "alice", 500_000, "Buy $TSLA", "2026-01-01T12:00:00", "TSLA")
        ok = store_tweet(conn, "1", "alice", 500_000, "Buy $TSLA", "2026-01-01T12:00:00", "TSLA")
        assert ok is False


class TestStoreSnapshot:
    def test_insert(self, conn):
        store_tweet(conn, "1", "alice", 500_000, "text", "2026-01-01T12:00:00", None)
        store_snapshot(conn, "1", likes=100, retweets=20)
        rows = conn.execute("SELECT * FROM tweet_snapshots WHERE tweet_id='1'").fetchall()
        assert len(rows) == 1
        assert rows[0][3] == 100  # likes
        assert rows[0][4] == 20   # retweets

    def test_multiple_snapshots(self, conn):
        store_tweet(conn, "1", "alice", 500_000, "text", "2026-01-01T12:00:00", None)
        store_snapshot(conn, "1", likes=100, retweets=20)
        store_snapshot(conn, "1", likes=200, retweets=40)
        rows = conn.execute("SELECT * FROM tweet_snapshots WHERE tweet_id='1'").fetchall()
        assert len(rows) == 2


class TestStorePriceSnapshot:
    def test_insert(self, conn):
        store_tweet(conn, "1", "alice", 500_000, "text", "2026-01-01T12:00:00", "TSLA")
        store_price_snapshot(conn, "1", "TSLA", "2026-01-01T12:05:00", 250.50, 10000)
        rows = conn.execute("SELECT * FROM price_snapshots WHERE tweet_id='1'").fetchall()
        assert len(rows) == 1
        assert rows[0][4] == pytest.approx(250.50)


class TestGetTrackedTweetIds:
    def test_returns_ids(self, conn):
        store_tweet(conn, "1", "a", 100, "t", "2026-01-01T12:00:00", None)
        store_tweet(conn, "2", "b", 200, "t", "2026-01-01T13:00:00", None)
        ids = get_tracked_tweet_ids(conn)
        assert set(ids) == {"1", "2"}

    def test_empty(self, conn):
        assert get_tracked_tweet_ids(conn) == []
