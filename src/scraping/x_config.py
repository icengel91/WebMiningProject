"""Configuration for the X/Twitter crawler.

All tuneable knobs live here so the crawler modules stay clean.
Account credentials come from environment variables (never hardcoded).
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / "configs" / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

# ---------------------------------------------------------------------------
# Search queries — cashtags, hashtags, and known accounts
# ---------------------------------------------------------------------------

QUERIES: list[str] = [
    # ---------------------------------------------------------------------------
    # Energie / Oil & Gas
    # ---------------------------------------------------------------------------
    "#oilprice lang:en",
    "#energystocks lang:en",
    "#crudeoil lang:en",
    "#Ölpreis lang:de",
    "#Energie lang:de",
    "$XOM lang:en",     # ExxonMobil
    "$CVX lang:en",     # Chevron
    "$SHEL lang:en",    # Shell
    "$BP lang:en",      # BP
    "$RWE lang:de OR lang:en",   # RWE (DE)

    # ---------------------------------------------------------------------------
    # Ölpumpen / Oilfield Services
    # ---------------------------------------------------------------------------
    "#oilfieldservices lang:en",
    "#Ölförderung lang:de",
    "$BKR lang:en",     # Baker Hughes

    # ---------------------------------------------------------------------------
    # Erneuerbare Energien / Renewables
    # ---------------------------------------------------------------------------
    "#renewableenergy lang:en",
    "#solarenergy lang:en",
    "#ErneuerbareEnergien lang:de",
    "#Solarenergie lang:de",
    "$ENPH lang:en",    # Enphase Energy
    "$SEDG lang:en",    # SolarEdge

    # ---------------------------------------------------------------------------
    # Edelmetalle / Precious Metals
    # ---------------------------------------------------------------------------
    "#gold lang:en",
    "#silver lang:en",
    "#preciousmetals lang:en",
    "#Goldpreis lang:de",
    "$GLD lang:en",     # Gold ETF
    "$SLV lang:en",     # Silver ETF
    "$NEM lang:en",     # Newmont (Gold)
    "$GOLD lang:en",    # Barrick Gold

    # ---------------------------------------------------------------------------
    # Waffenindustrie / Defense
    # ---------------------------------------------------------------------------
    "#defensestocks lang:en",
    "#defense lang:en",
    "#Rüstung lang:de",
    "$LMT lang:en",     # Lockheed Martin
    "$RTX lang:en",     # Raytheon
    "$NOC lang:en",     # Northrop Grumman
    "$RHM lang:de OR lang:en",   # Rheinmetall (DE)

    # ---------------------------------------------------------------------------
    # Automobil / Electric Vehicles + Ölpreis-Kontext
    # ---------------------------------------------------------------------------
    "#EVstocks lang:en",
    "#electricvehicle lang:en",
    "#Elektroauto lang:de",
    "#Autoindustrie lang:de",
    "$TSLA lang:en",    # Tesla
    "$NIO lang:en",     # NIO
    "$RIVN lang:en",    # Rivian
    "$BYDDF lang:en",   # BYD
    "$VWAGY lang:en",   # Volkswagen
    "$BMWYY lang:en",   # BMW
    "$TM lang:en",      # Toyota
]

# Minimum follower count to keep a tweet (filters out low-influence noise)
MIN_FOLLOWERS: int = 100
# Minimum likes a tweet must have to be stored (0 = no filter)
MIN_LIKES: int = 100

# Path to a custom Chromium executable — required on ARM (e.g. Raspberry Pi).
# Leave empty to use Playwright's bundled Chromium (x86/x64 only).
# Example: /usr/bin/chromium-browser
CHROMIUM_EXECUTABLE: str = os.environ.get("CHROMIUM_EXECUTABLE", "")
# ---------------------------------------------------------------------------
# Polling parameters
# ---------------------------------------------------------------------------

POLL_INTERVAL_MINUTES: int = 15       # Re-crawl interval per tweet
POLL_DURATION_MINUTES: int = 120      # Total tracking window per tweet

# ---------------------------------------------------------------------------
# Price window around each tweet
# ---------------------------------------------------------------------------

PRICE_OFFSET_BEFORE_MINUTES: int = 30
PRICE_OFFSET_AFTER_MINUTES: int = 120

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

REQUEST_DELAY_MIN: float = 1.5        # Seconds between API calls (lower bound)
REQUEST_DELAY_MAX: float = 3.0        # Seconds between API calls (upper bound)

# Maximum tweets to fetch per query in one discovery pass
DISCOVERY_LIMIT: int = 500

# ---------------------------------------------------------------------------
# twscrape account pool
# ---------------------------------------------------------------------------

def get_twscrape_accounts() -> list[dict[str, str]]:
    """Load twscrape account credentials from the TWSCRAPE_ACCOUNTS env var.

    Expected format (JSON array — ``cookies`` is optional but recommended):
        [{"username": "u", "password": "p", "email": "e",
          "email_password": "ep", "cookies": "ct0=…;auth_token=…"}]

    When ``cookies`` contains a valid ``ct0`` token, twscrape marks the
    account as active immediately and skips the login / email-verification
    flow — so ``password`` and ``email_password`` can be dummy values.

    Returns an empty list if the variable is not set.
    """
    raw = os.environ.get("TWSCRAPE_ACCOUNTS", "")
    if not raw:
        logger.warning(
            "TWSCRAPE_ACCOUNTS env var not set. "
            "Add your account(s) as a JSON array in configs/.env"
        )
        return []
    try:
        accounts = json.loads(raw)
        logger.info("Loaded %d twscrape account(s) from env.", len(accounts))
        return accounts
    except json.JSONDecodeError:
        logger.error("TWSCRAPE_ACCOUNTS is not valid JSON — check configs/.env")
        return []
