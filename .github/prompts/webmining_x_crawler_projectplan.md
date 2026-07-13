# Web Mining — Project Plan

## Research Question

Does X (Twitter) sentiment for energy/EV/auto stocks predict or follow price movements?

## Status

| Phase | Status |
|-------|--------|
| X crawler (twscrape + SQLite) | ✓ Complete |
| Price fetcher (yfinance) | ✓ Complete |
| NB01 — Data Quality EDA | ✓ Complete |
| NB02 — Sentiment Analysis (XLM-RoBERTa + VADER) | ✓ Complete |
| NB03 — Correlation Modeling | ✓ Complete |
| Final report (German) | ⏳ In progress |

## Focus Tickers (12)

TSLA, VWAGY, XOM, BYDDY, BP, TTE, 6503.T, 6367.T, E, CARR, SHEL, NIBE-B.ST

## Key Methodological Decisions

- Sentiment signal: `weighted_xlm_compound` (follower-weighted XLM score)
- Language filter: langdetect; VADER EN-only
- Min 10 aligned days per ticker; Granger needs ≥30
- Lag analysis: 0–3 trading days; event study ±5 days around >1σ spikes

## Core Finding

No significant correlations for most tickers. Only 6367.T Lag 1 is significant (r = −0.636, p = 0.048). No Granger causality in either direction. Likely cause: short data overlap (~4 months).

## Report Outline

1. Einleitung & Forschungsfrage
2. Datenbasis & Methodik
3. Ergebnisse (NB02 + NB03)
4. Diskussion (Limitierungen, Confounding, kurzes Zeitfenster)
5. Fazit
