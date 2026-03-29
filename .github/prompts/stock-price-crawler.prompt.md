---
description: "Guide and scaffold stock price retrieval using yfinance — covers module structure, rate limiting, data storage, and alignment with sentiment timelines."
agent: "agent"
tools: [search, file]
---

# Stock Price Crawler Development Guide

You are helping build the **finance data collection module** for a Web Mining university project that correlates social media sentiment with stock price movements.

## Project Context

- Target module: `src/finance/`
- Library: **yfinance** (already in `requirements.txt`)
- Config helper: `src/utils/config.py` (loads `.env` via `python-dotenv`)
- Data output directory: `data/` (gitignored)

## Implementation Checklist

When asked to implement or extend the stock price crawler, follow these steps:

### 1. Module Design (`src/finance/`)

- Create a `price_fetcher.py` with a public function to download OHLCV data for one or more tickers over a configurable date range.
- Accept parameters: `tickers: list[str]`, `start: str`, `end: str`, `interval: str` (default `"1d"`).
- Return a `pandas.DataFrame` with a consistent schema (`Date`, `Ticker`, `Open`, `High`, `Low`, `Close`, `Volume`).
- Use `logging` (no `print()`), `pathlib.Path` for file paths, and type hints on all public functions.

### 2. Rate Limiting & Resilience

- Respect Yahoo Finance's unofficial rate limits — add a configurable delay between batch requests (`time.sleep`).
- Wrap API calls in retry logic (e.g., `tenacity` or manual backoff) to handle transient HTTP errors.
- Log warnings on missing data or delisted tickers instead of raising hard exceptions.

### 3. Data Storage

- Persist fetched data to `data/raw/prices/` as **CSV** (one file per ticker or a combined file — be consistent).
- Include a metadata header or sidecar (JSON) recording: fetch timestamp, date range requested, yfinance version, and row count.
- Ensure the storage function is idempotent — re-running with the same parameters should overwrite or deduplicate, not append duplicates.

### 4. Reproducibility & Alignment

- Pin the exact date range used so sentiment and price data cover the same window.
- Normalize timestamps to **UTC** and date-only granularity (`YYYY-MM-DD`) for easy joining with sentiment DataFrames.
- Document the tickers and date range in a config file or constant so other team members can reproduce.

### 5. Testing

- Write `tests/test_price_fetcher.py` with at least:
  - A unit test that mocks `yfinance.download` and verifies output schema.
  - A test for retry behavior on simulated HTTP failure.
- Use `pytest` fixtures for reusable test data.

### 6. Things to Watch Out For

- **Adjusted vs. unadjusted close**: Prefer `Adj Close` for analysis to account for splits/dividends; document which column is used.
- **Weekend / holiday gaps**: Stock markets are closed on weekends. Don't treat missing weekend rows as errors.
- **yfinance breaking changes**: The library scrapes Yahoo Finance and can break without notice. Pin the version and note the last verified working date.
- **No API keys needed** for yfinance, but respect Yahoo's ToS — do not hammer the endpoint.
- **Data licensing**: Yahoo Finance data is for personal/research use. Note this in `docs/`.
