# Stock Price Crawler

Automated collection of daily OHLCV (Open, High, Low, Close, Volume) stock-price data from Yahoo Finance. The module feeds historical and ongoing price data into the sentiment–price correlation analysis pipeline.

---

## Table of Contents

1. [Overview](#overview)
2. [Data Columns](#data-columns)
3. [Architecture](#architecture)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Scheduling & Automation](#scheduling--automation)
7. [Storage & Deduplication](#storage--deduplication)
8. [Testing](#testing)
9. [Rate Limiting](#rate-limiting)

---

## Overview

The crawler downloads daily stock prices via the [yfinance](https://github.com/ranaroussi/yfinance) library, which scrapes Yahoo Finance. It is designed to run **three times per day** (09:30, 13:00, 17:00 UTC) to capture intraday corrections and late adjustments from Yahoo's data feed.

All data is stored in a **single, incrementally growing CSV file** (`data/raw/prices/prices.csv`). Each run only fetches data newer than what is already on disk, and duplicates are automatically removed.

### Why Three Runs Per Day?

Yahoo Finance may revise closing prices after the market session ends (e.g. adjusted close recalculations, delayed volume corrections). Running multiple times ensures we capture the most accurate final values for each trading day.

---

## Data Columns

Each row in `prices.csv` represents one ticker on one trading day:

| Column      | Description                                                       |
|-------------|-------------------------------------------------------------------|
| `Date`      | Trading day in UTC (`YYYY-MM-DD`)                                 |
| `Ticker`    | Yahoo Finance symbol (e.g. `AAPL`, `MSFT`)                       |
| `Open`      | Price at market open                                              |
| `High`      | Highest price reached during the trading session                  |
| `Low`       | Lowest price reached during the trading session                   |
| `Close`     | Price at market close                                             |
| `Adj Close` | Close price adjusted for stock splits and dividends — **use this for analysis** |
| `Volume`    | Total number of shares traded that day                            |

### Why Use Adj Close?

Corporate actions like stock splits (e.g. a 4:1 split makes each share worth ¼ of the previous price) and dividend payouts cause discontinuities in the raw `Close` price. `Adj Close` back-adjusts for these events, giving a continuous price series suitable for calculating returns and correlations.

---

## Architecture

```
src/finance/
├── __init__.py          # Public API re-exports
├── price_fetcher.py     # Core fetch, save, and deduplication logic
└── scheduler.py         # CLI entry point and 3× daily scheduler

configs/
└── tickers.yml          # Ticker list and start date (single source of truth)

data/raw/prices/
├── prices.csv           # Accumulated OHLCV data (gitignored, auto-generated)
└── prices_meta.json     # Metadata: last update, row count, date range

.github/workflows/
└── fetch-prices.yml     # GitHub Actions cron workflow
```

### Module Responsibilities

| Module | Role |
|--------|------|
| `price_fetcher.fetch_prices()` | Downloads OHLCV data per ticker via yfinance. Handles incremental start-date calculation, error recovery, and column normalisation. |
| `price_fetcher.save_prices()` | Merges new data into the existing CSV, deduplicates on `(Date, Ticker)`, writes metadata JSON. |
| `price_fetcher.fetch_and_save()` | Convenience wrapper — loads existing data once, passes it to both `fetch_prices()` and `save_prices()` to avoid redundant disk reads. |
| `scheduler.main()` | CLI entry point with `--once` and `--tickers` flags. Builds the 3× daily schedule or runs a single immediate job. |

---

## Configuration

### Ticker List — `configs/tickers.yml`

```yaml
tickers:
  - AAPL
  - MSFT
  - GOOGL
  - AMZN
  - TSLA
  - META
  - NVDA

start_date: "2024-01-01"
```

- **`tickers`**: Yahoo Finance symbols to fetch. Add or remove entries here — no code changes needed.
- **`start_date`**: Earliest date to fetch when no prior data exists for a ticker. Once data is collected, incremental mode takes over automatically.

This file is **required**. The module raises `FileNotFoundError` if it is missing.

### CLI Ticker Override

You can temporarily override tickers without editing the YAML:

```bash
python -m src.finance.scheduler --once --tickers AAPL TSLA
```

This is useful for one-off fetches or debugging a specific ticker.

---

## Usage

### Prerequisites

```bash
python -m venv .venv
source .venv/bin/activate    # Linux/Mac
pip install -r requirements.txt
```

### Single Fetch (Recommended for Manual Runs)

```bash
python -m src.finance.scheduler --once
```

Fetches all tickers defined in `configs/tickers.yml`, saves to `data/raw/prices/prices.csv`, and exits.

### Foreground Scheduler

```bash
python -m src.finance.scheduler
```

Runs in the foreground, executing at 09:30, 13:00, and 17:00 UTC daily. Stop with `Ctrl-C`.

### Background Scheduler

```bash
nohup python -m src.finance.scheduler > scheduler.log 2>&1 &
```

### Programmatic Usage

```python
from src.finance import fetch_and_save, fetch_prices

# Full incremental run
path = fetch_and_save()

# Fetch without saving (e.g. for analysis in a notebook)
df = fetch_prices(tickers=["AAPL", "MSFT"], start="2024-01-01", end="2024-06-01")
```

---

## Scheduling & Automation

### GitHub Actions (Primary Method)

The workflow at `.github/workflows/fetch-prices.yml` runs automatically on weekdays:

| Cron              | Time (UTC) | Purpose              |
|-------------------|------------|----------------------|
| `30 9 * * 1-5`   | 09:30      | After EU market open |
| `0 13 * * 1-5`   | 13:00      | US market open       |
| `0 17 * * 1-5`   | 17:00      | Near US market close |

Each run:
1. Checks out the repository
2. Installs dependencies
3. Runs `python -m src.finance.scheduler --once`
4. Commits and pushes any new data to the branch

### Manual Trigger

The workflow supports `workflow_dispatch` with optional inputs:
- **`branch`**: Branch to run on (default: `feature/stocks-crawling`)
- **`tickers`**: Space-separated ticker override (leave empty for default)

Trigger via GitHub UI: *Actions → Fetch stock prices → Run workflow*.

---

## Storage & Deduplication

### Incremental Strategy

The system avoids re-downloading historical data:

1. On each run, `_load_existing()` reads the current `prices.csv`
2. For each ticker, `_last_date_for_ticker()` finds the most recent stored date
3. Only data **after** that date is requested from Yahoo Finance
4. If a ticker is fully up-to-date, it is skipped entirely

### Deduplication

When saving, `save_prices()` merges old and new data and removes duplicates:

```
combined = concat(existing, new_data)
combined.drop_duplicates(subset=["Date", "Ticker"], keep="last")
```

The `keep="last"` strategy means fresher data always wins — if Yahoo revises a value in a later run, the updated value replaces the old one.

### Metadata

Each save writes `prices_meta.json` alongside the CSV:

```json
{
  "updated_at": "20240615T173000Z",
  "tickers": ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"],
  "total_rows": 3927,
  "date_min": "2024-01-02",
  "date_max": "2024-06-14",
  "yfinance_version": "0.2.36"
}
```

### Storage Estimates

| Tickers | Timeframe | Approx. Rows | CSV Size |
|---------|-----------|--------------|----------|
| 7       | 1 year    | ~1,750       | ~150 KB  |
| 50      | 1 year    | ~12,500      | ~1 MB    |
| 50      | 5 years   | ~62,500      | ~5 MB    |

Well within GitHub's 100 MB per-file and 5 GB repository limits.

---

## Testing

```bash
python -m pytest tests/test_price_fetcher.py -v
```

All tests use `unittest.mock.patch` to replace external dependencies (Yahoo Finance API, file system, time delays) with controlled fakes. No network access or real files are needed.

| Test | What It Verifies |
|------|-----------------|
| `test_returns_tidy_dataframe` | Output has correct columns, ticker labels, and is non-empty |
| `test_handles_empty_response` | Gracefully returns empty DataFrame for unknown tickers |
| `test_handles_download_exception` | Network errors don't crash — returns empty DataFrame |
| `test_multiple_tickers` | Fetching N tickers produces N × rows with correct labels |
| `test_incremental_skips_up_to_date_ticker` | Tickers with data up to end date are skipped (no API call) |
| `test_writes_csv_and_meta` | CSV and metadata JSON are written correctly |
| `test_deduplicates_on_merge` | Overlapping date/ticker rows are deduplicated |
| `test_returns_none_when_no_data_and_no_file` | Returns `None` when nothing fetched and no prior file exists |

---

## Rate Limiting

Yahoo Finance is an unofficial API and may throttle aggressive requests. The crawler implements:

- **1.5-second delay** between individual ticker downloads (`REQUEST_DELAY_SECONDS`)
- **Per-ticker sequential fetching** (no parallel requests)
- **Graceful error handling** — failed tickers are logged and skipped, not retried in the same run

For 7 tickers, a full initial fetch takes ~10 seconds. Incremental runs where most tickers are up-to-date complete in under 2 seconds.
