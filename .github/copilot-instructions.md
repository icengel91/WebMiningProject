# Project Guidelines

## Overview

University project for the **Web Mining** module (M.Sc. Data Science). The project analyzes how **stock prices** react to **social media sentiment** from Reddit, X (Twitter), and news sites.

## Tech Stack

- **Language**: Python 3.11+
- **Data collection**: Web scraping and API-based ingestion (Reddit API / PRAW, X API / Tweepy, news APIs or scrapers)
- **NLP / Sentiment**: transformers (Hugging Face), VADER, or similar sentiment pipelines
- **Data processing**: pandas, numpy
- **Visualization**: matplotlib, seaborn, plotly
- **Notebooks**: Jupyter notebooks for exploration and presentation
- **Finance data**: yfinance or similar for historical asset prices

## Architecture

```
data/              # Raw and processed datasets (gitignored)
notebooks/         # Jupyter notebooks for EDA, modeling, results
src/               # Reusable Python modules
  scraping/        #   Data collection from social media & news
  sentiment/       #   Sentiment analysis pipelines
  finance/         #   Asset price retrieval and alignment
  utils/           #   Shared helpers (logging, config, rate limiting)
tests/             # Unit and integration tests
configs/           # API keys template, scraping configs (no secrets!)
docs/              # Project documentation, reports
```

## Build and Test

```bash
# Setup
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
.venv\Scripts\activate      # Windows
pip install -r requirements.txt

# Run tests
pytest tests/

# Run a notebook
jupyter notebook notebooks/
```

## Conventions

- **No API keys in code or git.** Use environment variables or a `.env` file (gitignored). Provide a `configs/.env.example` template.
- **Respect rate limits.** All scrapers must implement backoff/retry logic and honor API rate limits.
- **Reproducibility.** Pin dependencies in `requirements.txt`. Seed random generators. Document data collection dates.
- **Notebook hygiene.** Clear outputs before committing. Keep notebooks focused—heavy logic belongs in `src/`.
- **Ethical scraping.** Respect `robots.txt`, Terms of Service, and do not collect personal data beyond what's publicly available.
- **German + English.** Code and comments in English; final report may be in German per university requirements.

## Code Style

- Follow PEP 8. Use type hints for function signatures.
- Prefer `pathlib.Path` over `os.path`.
- Use `logging` module instead of `print()` for operational output.
- Docstrings for public functions (Google style).

## Key Domain Concepts

- **Sentiment–price correlation**: Mapping social media sentiment scores to asset price movements over time windows.
- **Event detection**: Identifying spikes in social media activity that precede or follow price changes.
- **Multi-source fusion**: Combining signals from Reddit, X, and news into a unified sentiment timeline.
