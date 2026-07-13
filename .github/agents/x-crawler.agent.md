---
description: "Reference for the X/Twitter crawler (complete). Use when debugging src/scraping/."
tools: [read, search]
---

# X Crawler — Completed

Data collection ran Jan–May 2026; 2,266 focus-ticker tweets stored in SQLite.

## Key Files

- `src/scraping/x_crawler.py` — discovery & engagement polling via twscrape
- `src/scraping/db.py` — SQLite schema and helpers
- `src/scraping/x_config.py` — queries, thresholds, account pool

## Re-run

```bash
source .venv/bin/activate && python src/scraping/main.py
```

Requires `.env` with twscrape credentials. Backoff/retry is built in.
