# Project Guidelines

## Overview

University project for the **Web Mining** module (M.Sc. Data Science). Analyzes whether X (Twitter) sentiment predicts stock price movements for 12 Focus Tickers in the energy/EV/auto sector.

**Status:** Data collection ✓ | NB01 EDA ✓ | NB02 Sentiment ✓ | NB03 Correlation ✓ | **Report in progress**

## Tech Stack

- **Python** 3.12.3
- **Data collection**: twscrape (X/Twitter), yfinance (prices)
- **Storage**: SQLite, CSV (`data/raw/prices/`), Parquet (`data/processed/`)
- **Sentiment**: `cardiffnlp/twitter-xlm-roberta-base-sentiment` + VADER (EN-only baseline)
- **Stats**: scipy (Pearson/Spearman), statsmodels (Granger)
- **Viz**: matplotlib, seaborn

## Architecture

```
data/processed/    tweets_with_sentiment.parquet (2,266 rows)
                   daily_sentiment.parquet (508 rows, 12 tickers)
                   correlation_results / granger_results / event_study_results .parquet
notebooks/         01_data_quality_eda.ipynb
                   02_sentiment_analysis.ipynb
                   03_correlation_modeling.ipynb
src/scraping/      x_crawler.py, db.py, x_config.py
src/finance/       price_fetcher.py
```

## Build & Test

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/
```

## Conventions

- No secrets in code — `.env` (gitignored), see `configs/.env.example`
- PEP 8, type hints, `pathlib.Path`, `logging`, Google-style docstrings
- Clear notebook outputs before committing

## Key Results (NB03)

| Finding | Value |
|---------|-------|
| Aligned observations | 274 (8 tickers, ≥10 days) |
| Strongest correlation | 6367.T Lag 1, r = −0.636 (p = 0.048) |
| Granger causality | None significant (all p > 0.30) |
| Event study | Mixed CAR patterns, no consistent signal |

Short overlap (~4 months) limits statistical power — discuss in report.
