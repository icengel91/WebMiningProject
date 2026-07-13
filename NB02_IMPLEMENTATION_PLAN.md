# NB02 Sentiment Analysis — Implementierungsplan (Phase 2, Punkte 1 & 2)

## Phase 2 — Punkt 1: Komplette NB02-Pipeline (Baseline)

### Ziel
Die gesamte Sentiment-Analyse-Pipeline ausführen (Punkt 1 = aktueller Stand), um:
- Tweets zu laden und zu filtern (Bot-Kandidaten)
- Focus-Tickers zuzuweisen
- XLM-RoBERTa Sentiment-Inferenz durchzuführen
- VADER-Baseline zu berechnen
- Visualisierungen zu generieren
- Tägliche Aggregate zu berechnen
- **Ein Sentiment-Dataset** zu speichern: `tweets_with_sentiment.parquet`

### Checkpoint nach Punkt 1
Nach erfolgreicher Ausführung sollten folgende Dateien existieren:
```
data/processed/tweets_with_sentiment.parquet    (alle Tweets mit Sentiment-Spalten)
data/processed/daily_sentiment.parquet          (tägliche Aggregate, alle Tweets gemischt)
```

### Zu überprüfende Punkte in NB02:

| Bereich | Zelle(n) | Zu checken |
|---------|---------|-----------|
| **Setup** | 3 | ✓ Bot-Filter funktioniert (ist_bot_candidate Spalte existiert) |
| **Ticker-Zuweisung** | 4–6 | ✓ `focus_ticker` Spalte existiert für alle Tweets |
| **Content-Filter** | 7 | ✓ `has_content` Spalte (≥20 Zeichen) |
| **XLM-Modell** | 8–9 | ✓ Modell lädt erfolgreich |
| **Inferenz** | 10 | ✓ `sentiment_label`, `xlm_compound` Spalten gefüllt |
| **VADER** | 11 | ✓ `vader_compound`, `vader_label` Spalten gefüllt |
| **XLM vs VADER** | 12 | ✓ Übereinstimmungsmetriken berechnet |
| **Visualisierungen** | 13–15 | ✓ Label-Verteilung, Zeitreihen, Spot-Check angezeigt |
| **Daily Aggregate** | 16–17 | ✓ `daily` DataFrame mit allen Aggregaten |
| **Speichern** | 18 | ✓ Dateien geschrieben, Pfade geprüft |
| **Summary** | 19 | ✓ Zusammenfassung angezeigt |

---

## Phase 2 — Punkt 2: Retweets SEPARAT verarbeiten (Neue Infrastruktur)

### Ziel
Nach erfolgreicher Punkt-1-Ausführung: **Zwei separate Sentiment-Datasets** erzeugen:
- `tweets_with_sentiment_original.parquet` (Tweets mit `is_retweet == False`)
- `tweets_with_sentiment_retweets.parquet` (Tweets mit `is_retweet == True`)
- `daily_sentiment_original.parquet` (tägliche Aggregate, nur Original-Tweets)
- `daily_sentiment_retweets.parquet` (tägliche Aggregate, nur Retweets)

### Neue Cells (nach Punkt 1 abgeschlossen)

#### **Neue Zelle A: `is_retweet` Flag laden/prüfen**
```python
# Nach der Content-Filter-Zelle (Zelle 7)
# ── Retweet-Detection ────────────────────────────────────────────────────────
# is_retweet Flag sollte bereits aus NB01 in der DB sein
# Falls nicht vorhanden, konstruieren wir es aus dem Tweet-Content

if "is_retweet" not in tweets.columns:
    tweets["is_retweet"] = tweets["content"].fillna("").str.startswith("RT @")
    print("is_retweet Spalte aus Content rekonstruiert (DB hatte kein Flag)")
else:
    print("✓ is_retweet Spalte vorhanden")

# Statistik
n_rt = tweets["is_retweet"].sum()
n_orig = (~tweets["is_retweet"]).sum()
print(f"\nRetweet-Verteilung:")
print(f"  Original-Tweets:  {n_orig:,}  ({n_orig/(n_orig+n_rt):.1%})")
print(f"  Retweets:         {n_rt:,}  ({n_rt/(n_orig+n_rt):.1%})")
```

#### **Neue Zelle B: Split in Original vs. Retweets (nach Punkt 1 abgeschlossen)**
```python
# Nach Zelle 19 (Summary), vor Punkt 2

# ── Phase 2: Punkt 2 — Separate Verarbeitung ──────────────────────────────────
print("\n" + "="*80)
print("PHASE 2 — PUNKT 2: RETWEETS SEPARAT VERARBEITEN")
print("="*80 + "\n")

# Split focus_tweets in zwei Gruppen
focus_tweets_original = focus_tweets[~focus_tweets["is_retweet"]].copy()
focus_tweets_retweets = focus_tweets[focus_tweets["is_retweet"]].copy()

print(f"Split nach is_retweet:")
print(f"  Original-Tweets:  {len(focus_tweets_original):,}")
print(f"  Retweets:         {len(focus_tweets_retweets):,}")

# Sentiment-Verteilung pro Track
for track_name, track_df in [("Original", focus_tweets_original), ("Retweets", focus_tweets_retweets)]:
    valid = track_df["sentiment_label"].notna().sum()
    if valid > 0:
        print(f"\n{track_name}-Tweets mit Sentiment ({valid}):")
        print(track_df["sentiment_label"].value_counts().to_string())
```

#### **Neue Zelle C: Speichern zweier Sentiment-Datasets**
```python
# Zwei separate Parquet-Dateien

SENT_PATH_ORIG = OUT_DIR / "tweets_with_sentiment_original.parquet"
SENT_PATH_RT   = OUT_DIR / "tweets_with_sentiment_retweets.parquet"

focus_tweets_original.to_parquet(SENT_PATH_ORIG, index=False)
print(f"Saved tweets_with_sentiment_original → {SENT_PATH_ORIG}  ({len(focus_tweets_original):,} rows)")

focus_tweets_retweets.to_parquet(SENT_PATH_RT, index=False)
print(f"Saved tweets_with_sentiment_retweets → {SENT_PATH_RT}  ({len(focus_tweets_retweets):,} rows)")
```

#### **Neue Zelle D: Tägliche Aggregate — ORIGINAL**
```python
# Aggregation nur für Original-Tweets
ft_orig = focus_tweets_original.copy()
if ft_orig["posted_at"].dt.tz is not None:
    ft_orig["date"] = ft_orig["posted_at"].dt.tz_convert(None).dt.date
else:
    ft_orig["date"] = ft_orig["posted_at"].dt.date

daily_orig = (
    ft_orig.groupby(["focus_ticker", "date"])
    .agg(
        tweet_count        = ("tweet_id",         "count"),
        n_sentiment        = ("sentiment_label",  "count"),
        mean_xlm_compound  = ("xlm_compound",     "mean"),
        mean_sentiment_num = ("sentiment_num",    "mean"),
        pct_positive       = ("sentiment_label",  lambda x: (x == "positive").sum() / x.count() if x.count() > 0 else np.nan),
        pct_negative       = ("sentiment_label",  lambda x: (x == "negative").sum() / x.count() if x.count() > 0 else np.nan),
        mean_followers     = ("author_followers", "mean"),
    )
    .reset_index()
)

# VADER — nur EN-Tweets
_lang_col_orig = ft_orig["lang"] if "lang" in ft_orig.columns else pd.Series("und", index=ft_orig.index)
vader_en_orig = (
    ft_orig[_lang_col_orig == "en"]
    .groupby(["focus_ticker", "date"])
    .agg(mean_vader_en=("vader_compound", "mean"))
    .reset_index()
)
daily_orig = daily_orig.merge(vader_en_orig, on=["focus_ticker", "date"], how="left")

# Follower-gewichtet
ft_wt_orig = ft_orig[["focus_ticker", "date", "xlm_compound", "author_followers"]].copy()
ft_wt_orig["_w"]       = ft_wt_orig["author_followers"].fillna(0)
ft_wt_orig["_w_score"] = ft_wt_orig["xlm_compound"].fillna(0) * ft_wt_orig["_w"]

wt_agg_orig = (
    ft_wt_orig.groupby(["focus_ticker", "date"])
    .agg(_w_score_sum=("_w_score", "sum"), _w_sum=("_w", "sum"))
    .reset_index()
)
wt_agg_orig["weighted_xlm_compound"] = np.where(
    wt_agg_orig["_w_sum"] > 0,
    wt_agg_orig["_w_score_sum"] / wt_agg_orig["_w_sum"],
    np.nan,
)
daily_orig = daily_orig.merge(
    wt_agg_orig[["focus_ticker", "date", "weighted_xlm_compound"]],
    on=["focus_ticker", "date"], how="left",
)

daily_orig["date"] = pd.to_datetime(daily_orig["date"])

print(f"Daily sentiment (ORIGINAL): {len(daily_orig):,} rows")
print(f"Date range: {daily_orig['date'].min().date()} → {daily_orig['date'].max().date()}")
```

#### **Neue Zelle E: Tägliche Aggregate — RETWEETS**
```python
# Aggregation nur für Retweets (analog zu Zelle D)
ft_rt = focus_tweets_retweets.copy()
if ft_rt["posted_at"].dt.tz is not None:
    ft_rt["date"] = ft_rt["posted_at"].dt.tz_convert(None).dt.date
else:
    ft_rt["date"] = ft_rt["posted_at"].dt.date

daily_rt = (
    ft_rt.groupby(["focus_ticker", "date"])
    .agg(
        tweet_count        = ("tweet_id",         "count"),
        n_sentiment        = ("sentiment_label",  "count"),
        mean_xlm_compound  = ("xlm_compound",     "mean"),
        mean_sentiment_num = ("sentiment_num",    "mean"),
        pct_positive       = ("sentiment_label",  lambda x: (x == "positive").sum() / x.count() if x.count() > 0 else np.nan),
        pct_negative       = ("sentiment_label",  lambda x: (x == "negative").sum() / x.count() if x.count() > 0 else np.nan),
        mean_followers     = ("author_followers", "mean"),
    )
    .reset_index()
)

# VADER — nur EN-Tweets
_lang_col_rt = ft_rt["lang"] if "lang" in ft_rt.columns else pd.Series("und", index=ft_rt.index)
vader_en_rt = (
    ft_rt[_lang_col_rt == "en"]
    .groupby(["focus_ticker", "date"])
    .agg(mean_vader_en=("vader_compound", "mean"))
    .reset_index()
)
daily_rt = daily_rt.merge(vader_en_rt, on=["focus_ticker", "date"], how="left")

# Follower-gewichtet
ft_wt_rt = ft_rt[["focus_ticker", "date", "xlm_compound", "author_followers"]].copy()
ft_wt_rt["_w"]       = ft_wt_rt["author_followers"].fillna(0)
ft_wt_rt["_w_score"] = ft_wt_rt["xlm_compound"].fillna(0) * ft_wt_rt["_w"]

wt_agg_rt = (
    ft_wt_rt.groupby(["focus_ticker", "date"])
    .agg(_w_score_sum=("_w_score", "sum"), _w_sum=("_w", "sum"))
    .reset_index()
)
wt_agg_rt["weighted_xlm_compound"] = np.where(
    wt_agg_rt["_w_sum"] > 0,
    wt_agg_rt["_w_score_sum"] / wt_agg_rt["_w_sum"],
    np.nan,
)
daily_rt = daily_rt.merge(
    wt_agg_rt[["focus_ticker", "date", "weighted_xlm_compound"]],
    on=["focus_ticker", "date"], how="left",
)

daily_rt["date"] = pd.to_datetime(daily_rt["date"])

print(f"Daily sentiment (RETWEETS): {len(daily_rt):,} rows")
print(f"Date range: {daily_rt['date'].min().date()} → {daily_rt['date'].max().date()}")
```

#### **Neue Zelle F: Speichern zweier Daily-Datasets**
```python
DAILY_PATH_ORIG = OUT_DIR / "daily_sentiment_original.parquet"
DAILY_PATH_RT   = OUT_DIR / "daily_sentiment_retweets.parquet"

daily_orig.to_parquet(DAILY_PATH_ORIG, index=False)
print(f"Saved daily_sentiment_original → {DAILY_PATH_ORIG}  ({len(daily_orig):,} rows)")

daily_rt.to_parquet(DAILY_PATH_RT, index=False)
print(f"Saved daily_sentiment_retweets → {DAILY_PATH_RT}  ({len(daily_rt):,} rows)")
```

#### **Neue Zelle G: Vergleich Original vs. Retweets**
```python
# Vergleichsanalyse: Sentiment-Signal unterschiedlich für Original vs. Retweets?

print("\n" + "="*80)
print("VERGLEICH: Original-Tweets vs. Retweets")
print("="*80 + "\n")

# Aggregierte Metriken pro Track
comp_data = []
for track_name, daily_track in [("Original", daily_orig), ("Retweets", daily_rt)]:
    n_days = len(daily_track)
    n_tickers = daily_track["focus_ticker"].nunique()
    mean_sent = daily_track["mean_xlm_compound"].mean()
    std_sent = daily_track["mean_xlm_compound"].std()
    comp_data.append({
        "Track": track_name,
        "Tage": n_days,
        "Tickers": n_tickers,
        "mean_xlm": round(mean_sent, 4),
        "std_xlm": round(std_sent, 4),
    })

comp_df = pd.DataFrame(comp_data)
print(comp_df.to_string(index=False))

print("\nInterpretation:")
if abs(comp_df.iloc[0]["mean_xlm"] - comp_df.iloc[1]["mean_xlm"]) > 0.05:
    print("→ Signifikante Unterschiede im durchschnittlichen Sentiment zwischen Original & Retweets!")
else:
    print("→ Ähnliche durchschnittliche Sentiment-Signale")
```

---

## Umsetzungsreihenfolge

### Schritt 1: **Punkt 1 ausführen**
1. NB02 von Anfang bis Ende durchlaufen
2. Checkpoints überprüfen (Setup → Inferenz → Visualisierungen → Speichern)
3. Output-Dateien überprüfen:
   - `data/processed/tweets_with_sentiment.parquet` ✓
   - `data/processed/daily_sentiment.parquet` ✓

### Schritt 2: **Neue Zellen für Punkt 2 hinzufügen**
Nach erfolgreicher Punkt-1-Ausführung:
1. Zelle A: `is_retweet` Flag laden
2. Zelle B: Split in Original vs. Retweets
3. Zelle C: Speichern zweier Sentiment-Datasets
4. Zelle D: Daily Aggregate — Original
5. Zelle E: Daily Aggregate — Retweets
6. Zelle F: Speichern zweier Daily-Datasets
7. Zelle G: Vergleich Original vs. Retweets

### Schritt 3: **Verifikation**
Nach Punkt 2 sollten folgende Dateien existieren:
```
data/processed/
├── tweets_with_sentiment_original.parquet
├── tweets_with_sentiment_retweets.parquet
├── daily_sentiment_original.parquet
├── daily_sentiment_retweets.parquet
```

---

## Erwartete Output-Struktur nach Phase 2 Punkt 2

| Datei | Rows | Spalten | Zweck |
|-------|------|---------|-------|
| `tweets_with_sentiment_original.parquet` | ~1.5k | tweet_id, focus_ticker, sentiment_label, xlm_compound, vader_compound, ... | Original-Tweets mit Sentiment |
| `tweets_with_sentiment_retweets.parquet` | ~0.7k | tweet_id, focus_ticker, sentiment_label, xlm_compound, vader_compound, ... | Retweets mit Sentiment |
| `daily_sentiment_original.parquet` | ~300 | focus_ticker, date, mean_xlm_compound, pct_positive, ... | Tägliche Aggregate (Original) |
| `daily_sentiment_retweets.parquet` | ~200 | focus_ticker, date, mean_xlm_compound, pct_positive, ... | Tägliche Aggregate (Retweets) |

---

## Nächste Schritte nach Punkt 2

1. **NB03 ausführen** mit `daily_sentiment_original.parquet` (Primär-Analyse)
2. **Optional**: Separate Korrelationsanalyse mit `daily_sentiment_retweets.parquet` für Sensitivitätstest
3. **Report schreiben** mit Ergebnissen aus NB01/02/03
