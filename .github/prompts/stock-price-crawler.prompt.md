---
description: "Reference for the price fetcher module (complete)."
tools: [read, search]
---

# Stock Price Fetcher — Completed

Prices at `data/raw/prices/prices.csv` (18 tickers, 2024-01-01 → 2026-04-23).

| Field | Detail |
|-------|--------|
| Columns | Date, Ticker, Open, High, Low, Close, Adj Close, Volume |
| Key file | `src/finance/price_fetcher.py` |
| Scheduled updates | `src/finance/scheduler.py` |

Uses `Adj Close` for return calculations.
