# Web Mining Project – Asset Sentiment Analysis

University project for the **Web Mining** module (M.Sc. Data Science).

Analyzes how **stock prices** react to **social media sentiment** from Reddit, X (Twitter), and news sites.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
```

Copy `configs/.env.example` → `configs/.env` and fill in your API keys.

## Project Structure

```
data/              Raw and processed datasets (gitignored)
notebooks/         Jupyter notebooks for EDA, modeling, results
src/               Reusable Python modules
  scraping/          Data collection (Reddit, X, news)
  sentiment/         Sentiment analysis pipelines
  finance/           Asset price retrieval and alignment
  utils/             Shared helpers (logging, config, rate limiting)
tests/             Unit and integration tests
configs/           API key templates, scraping configs
docs/              Documentation and reports
```

## Running Tests

```bash
pytest tests/
```

## License

Academic use only – university project.
