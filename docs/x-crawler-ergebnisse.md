# X/Twitter Crawler — Erkenntnisse und Vorgehensweise

## Projektziel

Analyse des Zusammenhangs zwischen viralen Posts auf X (Twitter) und kurzfristigen
Aktienkursbewegungen. Der Crawler sammelt Tweets zu Aktienthemen, filtert nach
Reichweite und Popularität, und holt automatisch minütliche Kursdaten um den
Zeitpunkt jedes Tweets herum.

---

## Architektur

```
src/scraping/
  db.py          — SQLite-Schema und CRUD-Hilfsfunktionen
  x_config.py    — Alle Konfigurationsparameter (Schwellwerte, Queries, Delays)
  x_crawler.py   — Playwright-basierter Crawler (Discovery + Polling)
  main.py        — CLI-Einstiegspunkt

data/
  webmining.db   — SQLite-Datenbank (gitignored)

configs/
  .env           — Credentials (gitignored)
  .env.example   — Vorlage mit Dokumentation
```

### Datenbankschema

```sql
tweets(
  tweet_id        TEXT PRIMARY KEY,
  author          TEXT,
  author_followers INTEGER,
  content         TEXT,
  posted_at       TEXT,   -- ISO 8601 UTC
  symbol          TEXT    -- NULL wenn kein Cashtag erkannt
)

tweet_snapshots(
  id          INTEGER PRIMARY KEY,
  tweet_id    TEXT REFERENCES tweets,
  crawled_at  TEXT,
  likes       INTEGER,
  retweets    INTEGER
)

price_snapshots(
  id          INTEGER PRIMARY KEY,
  tweet_id    TEXT REFERENCES tweets,
  symbol      TEXT,
  timestamp   TEXT,   -- ISO 8601, minütlich
  price       REAL,   -- Close-Preis
  volume      INTEGER
)
```

---

## Technologie-Entscheidungen

### Scraping: Playwright statt API-Bibliotheken

**Ursprünglicher Plan**: Verwendung der Bibliotheken `twscrape` und `twikit` für
den Zugriff auf die inoffizielle X-API.

**Problem**: Beide Bibliotheken schlugen mit `IndexError: list index out of range`
fehl. X hatte die interne API-Struktur geändert, womit beide Bibliotheken
nicht mehr kompatibel waren.

**Lösung**: Umstieg auf **Playwright** (headless Chromium). Der Browser navigiert
zu `x.com/search` und extrahiert Tweet-Daten direkt aus dem DOM — unabhängig von
API-Änderungen.

### Authentifizierung: Cookie-basiert

**Problem**: Das X-Konto wurde über einen SimpleLogin-Alias registriert. Das echte
E-Mail-Passwort für den Verifizierungsflow war unbekannt.

**Lösung**: Cookie-basierte Authentifizierung. Die Werte `ct0` und `auth_token`
werden aus dem Browser (DevTools → Application → Cookies) kopiert und in die
`.env`-Datei eingetragen. Playwright injiziert diese Cookies, sodass X die Session
als eingeloggt erkennt — ohne Login-Flow.

```
TWSCRAPE_ACCOUNTS=[{"username": "handle", "cookies": "ct0=…;auth_token=…"}]
```

### Kursdaten: yfinance

Für jeden gespeicherten Tweet mit erkanntem Cashtag (`$TSLA`, `$NVDA`, etc.) werden
per `yfinance` minütliche OHLCV-Daten in einem Zeitfenster von ±30/120 Minuten
heruntergeladen und in `price_snapshots` gespeichert.

---

## Implementierte Filter

| Filter | Schwellwert | Zweck |
|---|---|---|
| `MIN_FOLLOWERS` | 1.000 | Rauschen durch Accounts mit geringer Reichweite filtern |
| `MIN_LIKES` | 500 | Nur Tweets mit messbarer Resonanz sammeln |

**Optimierung der Filter-Reihenfolge**: Der Likes-Filter benötigt keinen zusätzlichen
HTTP-Request (Likes sind auf der Suchergebnisseite sichtbar). Der Follower-Filter
hingegen erfordert einen Profilaufruf pro Account. Daher wird zuerst nach Likes
gefiltert, um unnötige Profilaufrufe zu vermeiden.

**Server-seitige Vorfilterung**: Der Operator `min_faves:<n>` wird direkt in die
X-Suchanfrage eingebaut (`#stocks lang:en min_faves:500`), damit X bereits nur
relevante Tweets zurückgibt.

---

## Erkannte Probleme und Lösungen

### Problem 1: Bot-Detection durch zu viele Profilaufrufe

**Symptom**: Die ersten zwei Queries lieferten Tweets, alle weiteren Queries
gaben `No tweets loaded` zurück. Zwischen Query 2 und 3 lag eine ~2-Minuten-Pause,
in der für alle 52 gescrapten Tweets Profilseiten aufgerufen wurden.

**Ursache**: X erkannte das Muster (52 schnelle Profilaufrufe) als Bot-Verhalten
und blockierte die Session für weitere Suchanfragen.

**Lösung**: Filter-Reihenfolge umgekehrt (Likes zuerst, dann Follower) und
`min_faves`-Operator in die Suchanfrage integriert. Dadurch werden drastisch
weniger Profilseiten aufgerufen.

---

### Problem 2: TypeError beim Kursabruf (yfinance MultiIndex)

**Symptom**:
```
TypeError: float() argument must be a string or a real number, not 'Series'
```

**Ursache**: Neuere yfinance-Versionen liefern bei `yf.download()` einen DataFrame
mit MultiIndex-Spalten: `("Close", "TSLA")` statt `"Close"`. Der Code versuchte
`float(row["Close"])`, was eine `Series` zurückgab statt einem Skalar.

**Lösung**: Spalten nach dem Download flatten:
```python
if isinstance(data.columns, pd.MultiIndex):
    data.columns = data.columns.get_level_values(0)
```

---

### Problem 3: "possibly delisted" — keine Kursdaten am Wochenende

**Symptom**: Für nahezu alle TSLA/NVDA-Tweets erschien:
```
ERROR yfinance  $TSLA: possibly delisted; no price data found
```

**Ursache**: Die gesammelten Tweets stammten vom Wochenende (27.–29. März 2026).
Die NYSE ist Mo–Fr von 09:30–16:00 ET (14:30–21:00 UTC) geöffnet.
yfinance findet für `1m`-Daten außerhalb der Handelszeiten keine Daten —
das ist kein Fehler, sondern erwartetes Verhalten.

**Lösung**: Logik zur Erkennung von Handelszeiten eingebaut:
- Fällt das Zeitfenster auf ein Wochenende oder außerhalb der NYSE-Handelszeiten →
  `INFO`-Meldung: "Märkte waren geschlossen"
- Fällt das Zeitfenster in die Handelszeiten, aber es kommen dennoch keine Daten →
  `WARNING`: möglicherweise Delisting oder Rate-Limiting

---

## Such-Queries

```python
QUERIES = [
    # Breite Hashtag-Suche — Cashtags werden automatisch aus dem Tweet-Text extrahiert
    "#stocks lang:en",
    "#stockmarket lang:en",
    "#trading lang:en",
    "#investing lang:en",
    "#wallstreetbets lang:en",
    "#aktien lang:de",
    "#boerse lang:de",
    # Hochprofile Cashtags als zuverlässiger Anker
    "$TSLA lang:en",
    "$NVDA lang:en",
    "$SAP lang:de OR lang:en",
]
```

**Strategie**: Breite Hashtag-Queries statt enger Cashtag-Listen. Cashtags
werden automatisch per Regex aus dem Tweet-Text extrahiert (`\$([A-Z]{1,5})\b`).
Das ermöglicht die Entdeckung unerwarteter viraler Aktien, die im Voraus nicht
bekannt sind.

---

## Ergebnisse (Stand 30. März 2026)

| Metrik | Wert |
|---|---|
| Gesammelte Tweets | ~60 (nach zweitem erfolgreichen Run) |
| Erkannte Symbole | TSLA, NVDA, ASTS, META, GOOGL, MSFT u.a. |
| Price Snapshots | 0 (Wochenende — keine Handelsdaten) |
| Engagement Snapshots | ~60 |

**Beobachtung**: Die deutschen Queries (`#aktien`, `#boerse`) lieferten zeitlich
ältere Tweets (teils Jahre alt), die dennoch die Like-Schwelle erfüllen. Die
englischen Queries speziell mit `$TSLA`/`$NVDA` lieferten aktuelle Tweets von
bekannten Finanzaccounts mit 15.000–1.300.000 Followern.

**Nächster Schritt**: Kursdaten werden sich automatisch füllen, sobald die Märkte
am Montag (30. März 2026, ab 15:30 Uhr MEZ) öffnen.

---

## Deployment

### Lokal (empfohlen für Uni-Projekt)

```bash
# Einmalig
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Crawler starten
python -m src.scraping.main --discover-only --limit 50

# Automatisierung per Cron (Mo–Fr, 09/12/15/18 Uhr)
# crontab -e
# 0 9,12,15,18 * * 1-5  cd /path/to/repo && .venv/bin/python -m src.scraping.main --discover-only --limit 50
```

### Raspberry Pi (ARM)

```bash
git clone <repo> WebMiningProject
cd WebMiningProject
bash setup_pi.sh  # installiert System-Chromium, venv, Cron-Job
```

Das Skript setzt `CHROMIUM_EXECUTABLE=/usr/bin/chromium-browser`, da Playwright
kein gebündeltes Chromium für ARM liefert.

### GitHub Actions (nicht empfohlen)

Drei Hindernisse machen GitHub Actions für dieses Setup unpraktisch:
1. **SQLite nicht persistent** — Container wird nach jedem Job gelöscht
2. **Cookie-Ablauf** — Secrets müssen alle 30–90 Tage manuell erneuert werden
3. **Bot-Detection** — Azure-IPs werden von X für Cookie-Sessions aus Heimnetzen geblockt

---

## Konfigurationsparameter

| Parameter | Wert | Bedeutung |
|---|---|---|
| `MIN_FOLLOWERS` | 1.000 | Mindest-Follower des Tweet-Autors |
| `MIN_LIKES` | 500 | Mindest-Likes des Tweets |
| `POLL_INTERVAL_MINUTES` | 15 | Wie oft Engagement re-gecrawlt wird |
| `POLL_DURATION_MINUTES` | 120 | Wie lange ein Tweet getrackt wird |
| `PRICE_OFFSET_BEFORE_MINUTES` | 30 | Kursfenster vor dem Tweet |
| `PRICE_OFFSET_AFTER_MINUTES` | 120 | Kursfenster nach dem Tweet |
| `DISCOVERY_LIMIT` | 500 | Max. Tweets pro Query pro Run |
| `REQUEST_DELAY_MIN/MAX` | 1,5–3,0 s | Verzögerung zwischen Requests |
