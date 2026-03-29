"""Fetch OHLCV stock-price data from Yahoo Finance via yfinance.

Data is stored in a **single** CSV file (``data/raw/prices/prices.csv``)
that grows incrementally.  Each run only fetches data newer than what is
already on disk and deduplicates on ``(Date, Ticker)`` so the file never
contains duplicate rows regardless of how often the scheduler fires.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PRICES_DIR = _PROJECT_ROOT / "data" / "raw" / "prices"
TICKERS_CONFIG = _PROJECT_ROOT / "configs" / "tickers.yml"

PRICES_CSV = RAW_PRICES_DIR / "prices.csv"
PRICES_META = RAW_PRICES_DIR / "prices_meta.json"


def _load_tickers_config() -> dict:
    """Load ticker configuration from ``configs/tickers.yml``."""
    if not TICKERS_CONFIG.exists():
        raise FileNotFoundError(
            f"Ticker config not found at {TICKERS_CONFIG}. "
            "Copy configs/tickers.yml and define your tickers there."
        )
    with TICKERS_CONFIG.open() as f:
        config = yaml.safe_load(f)
    logger.info("Loaded ticker config from %s.", TICKERS_CONFIG)
    return config or {}


_config = _load_tickers_config()

DEFAULT_TICKERS: list[str] = _config["tickers"]
DEFAULT_START: str = _config.get("start_date", "2024-01-01")

# Delay between individual ticker downloads to avoid throttling
REQUEST_DELAY_SECONDS: float = 1.5

COLUMN_ORDER: list[str] = [
    "Date",       # Trading day (UTC, YYYY-MM-DD)
    "Ticker",     # Stock symbol on Yahoo Finance (e.g. "AAPL")
    "Open",       # Price at market open
    "High",       # Highest price during the day
    "Low",        # Lowest price during the day
    "Close",      # Price at market close
    "Adj Close",  # Close adjusted for splits & dividends — use for analysis
    "Volume",     # Total shares traded that day
]


def _load_existing() -> pd.DataFrame:
    """Load the existing combined CSV, or return an empty DataFrame."""
    if PRICES_CSV.exists():
        df = pd.read_csv(PRICES_CSV, dtype={"Date": str})
        logger.info("Loaded %d existing rows from %s.", len(df), PRICES_CSV)
        return df
    return pd.DataFrame(columns=COLUMN_ORDER)


def _last_date_for_ticker(existing: pd.DataFrame, ticker: str) -> str | None:
    """Return the latest date string already stored for *ticker*."""
    if existing.empty or "Ticker" not in existing.columns:
        return None
    subset = existing.loc[existing["Ticker"] == ticker, "Date"]
    if subset.empty:
        return None
    return str(subset.max())


def fetch_prices(
    tickers: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
    incremental: bool = True,
    _existing: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Download OHLCV data for the given tickers.

    Args:
        tickers: List of Yahoo Finance ticker symbols.
                 Defaults to ``DEFAULT_TICKERS``.
        start: Start date string (``YYYY-MM-DD``). Defaults to ``DEFAULT_START``.
                Ignored per-ticker in incremental mode when prior data exists.
        end: End date string (``YYYY-MM-DD``). Defaults to today (UTC).
        interval: Bar size — ``"1d"``, ``"1h"``, ``"5m"``, etc.
        incremental: If ``True`` (default), only fetch data newer than what
                     is already stored in ``prices.csv``.
        _existing: Pre-loaded existing data (avoids redundant disk reads
                   when called from :func:`fetch_and_save`).

    Returns:
        A tidy ``DataFrame`` with columns
        ``[Date, Ticker, Open, High, Low, Close, Adj Close, Volume]``.
    """
    tickers = tickers or DEFAULT_TICKERS
    default_start = start or DEFAULT_START
    end = end or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if incremental:
        existing = _existing if _existing is not None else _load_existing()
    else:
        existing = pd.DataFrame(columns=COLUMN_ORDER)

    frames: list[pd.DataFrame] = []

    for ticker in tickers:
        # Determine per-ticker start date
        if incremental:
            last = _last_date_for_ticker(existing, ticker)
            if last:
                # Start one day after the last stored date to avoid overlap
                ticker_start = (
                    datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)
                ).strftime("%Y-%m-%d")
                if ticker_start > end:
                    logger.info("%s is up-to-date (last=%s).", ticker, last)
                    continue
            else:
                ticker_start = default_start
        else:
            ticker_start = default_start

        logger.info("Fetching %s  [%s → %s, interval=%s]", ticker, ticker_start, end, interval)
        try:
            data: pd.DataFrame = yf.download(
                ticker,
                start=ticker_start,
                end=end,
                interval=interval,
                progress=False,
                auto_adjust=False,
            )
        except Exception:
            logger.warning("Failed to download %s — skipping.", ticker, exc_info=True)
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        if not data.empty:
            # yfinance may return MultiIndex columns — flatten if necessary.
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            data = data.reset_index()
            data["Ticker"] = ticker

            # Normalise the date column to UTC, date-only
            if "Date" in data.columns:
                data["Date"] = pd.to_datetime(data["Date"], utc=True).dt.strftime("%Y-%m-%d")
            elif "Datetime" in data.columns:
                data.rename(columns={"Datetime": "Date"}, inplace=True)
                data["Date"] = pd.to_datetime(data["Date"], utc=True).dt.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            frames.append(data)
        else:
            logger.warning("No new data returned for %s.", ticker)

        time.sleep(REQUEST_DELAY_SECONDS)

    if not frames:
        logger.info("No new price data to add.")
        return pd.DataFrame(columns=COLUMN_ORDER)

    new_data = pd.concat(frames, ignore_index=True)
    present_cols = [c for c in COLUMN_ORDER if c in new_data.columns]
    new_data = new_data[present_cols]

    logger.info("Fetched %d new rows for %d tickers.", len(new_data), len(frames))
    return new_data


def save_prices(new_df: pd.DataFrame, existing: pd.DataFrame | None = None) -> Path:
    """Merge *new_df* into the single ``prices.csv`` and write metadata.

    Deduplicates on ``(Date, Ticker)`` keeping the latest values.

    Args:
        new_df: Newly fetched price rows.
        existing: Already-loaded CSV data. If ``None``, reads from disk.

    Returns:
        Path to the written CSV file.
    """
    RAW_PRICES_DIR.mkdir(parents=True, exist_ok=True)

    if existing is None:
        existing = _load_existing()
    combined = pd.concat([existing, new_df], ignore_index=True)

    # Deduplicate — keep last (newest fetch wins)
    combined.drop_duplicates(subset=["Date", "Ticker"], keep="last", inplace=True)
    combined.sort_values(["Ticker", "Date"], inplace=True)
    combined.reset_index(drop=True, inplace=True)

    combined.to_csv(PRICES_CSV, index=False)

    metadata = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "tickers": sorted(combined["Ticker"].unique().tolist()),
        "total_rows": len(combined),
        "date_min": str(combined["Date"].min()),
        "date_max": str(combined["Date"].max()),
        "yfinance_version": yf.__version__,
    }
    PRICES_META.write_text(json.dumps(metadata, indent=2))

    logger.info("Saved %d total rows → %s", len(combined), PRICES_CSV)
    return PRICES_CSV


def fetch_and_save(
    tickers: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
) -> Path | None:
    """Convenience wrapper: incrementally fetch prices then persist to disk.

    Returns:
        Path to the CSV file, or ``None`` if nothing was fetched.
    """
    existing = _load_existing()
    new_df = fetch_prices(
        tickers=tickers, start=start, end=end, interval=interval,
        incremental=True, _existing=existing,
    )
    if new_df.empty:
        logger.info("Nothing new — prices.csv unchanged.")
        return PRICES_CSV if PRICES_CSV.exists() else None
    return save_prices(new_df, existing=existing)
