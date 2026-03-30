#!/usr/bin/env bash
# setup_pi.sh — One-shot setup for Raspberry Pi (ARM)
#
# Usage:
#   git clone <repo-url> WebMiningProject
#   cd WebMiningProject
#   chmod +x setup_pi.sh
#   ./setup_pi.sh
#
# What this script does:
#   1. Installs system dependencies (Python venv, Chromium, NSSDB deps)
#   2. Creates a Python virtual environment (.venv)
#   3. Installs Python dependencies from requirements.txt
#   4. Installs Playwright's system-level browser dependencies (no ARM download)
#   5. Creates configs/.env from configs/.env.example if it doesn't exist yet
#   6. Optionally installs a cron job for weekday market-hours crawling
#
# After running this script, edit configs/.env and set your TWSCRAPE_ACCOUNTS cookie.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$REPO_DIR/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"
CRON_CMD="cd $REPO_DIR && $PYTHON -m src.scraping.main --discover-only --limit 50 >> $REPO_DIR/data/crawl.log 2>&1"
CRON_SCHEDULE="0 9,12,15,18 * * 1-5"

echo "=== WebMining Pi Setup ==="
echo "Project root: $REPO_DIR"
echo ""

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    chromium chromium-browser 2>/dev/null || \
sudo apt-get install -y --no-install-recommends chromium
sudo apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2 libpangocairo-1.0-0

echo "    System Chromium: $(chromium-browser --version 2>/dev/null || echo 'not found — check package name')"

# ---------------------------------------------------------------------------
# 2. Python virtual environment
# ---------------------------------------------------------------------------
echo "[2/6] Creating Python venv at $VENV..."
python3 -m venv "$VENV"

# ---------------------------------------------------------------------------
# 3. Python dependencies
# ---------------------------------------------------------------------------
echo "[3/6] Installing Python dependencies..."
"$PIP" install --upgrade pip --quiet
"$PIP" install -r "$REPO_DIR/requirements.txt" --quiet

# ---------------------------------------------------------------------------
# 4. Playwright (skip Chromium download — we use system Chromium on ARM)
# ---------------------------------------------------------------------------
echo "[4/6] Configuring Playwright (no Chromium download for ARM)..."
# Install only the system-level deps that Playwright needs; skip browser download
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 "$PYTHON" -m playwright install-deps chromium 2>/dev/null || true
echo "    Playwright configured to skip Chromium download (using system Chromium)."

# ---------------------------------------------------------------------------
# 5. .env file
# ---------------------------------------------------------------------------
echo "[5/6] Checking configs/.env..."
ENV_FILE="$REPO_DIR/configs/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$REPO_DIR/configs/.env.example" "$ENV_FILE"
    echo "    Created configs/.env from template."
    echo ""
    echo "    *** ACTION REQUIRED ***"
    echo "    Edit configs/.env and fill in your TWSCRAPE_ACCOUNTS cookie:"
    echo "      nano $ENV_FILE"
    echo ""
    # Pre-set CHROMIUM_EXECUTABLE for ARM
    CHROMIUM_PATH="$(command -v chromium-browser 2>/dev/null || command -v chromium 2>/dev/null || echo '')"
    if [[ -n "$CHROMIUM_PATH" ]]; then
        sed -i "s|^CHROMIUM_EXECUTABLE=.*|CHROMIUM_EXECUTABLE=$CHROMIUM_PATH|" "$ENV_FILE"
        echo "    Auto-set CHROMIUM_EXECUTABLE=$CHROMIUM_PATH"
    fi
else
    echo "    configs/.env already exists — skipping."
    # Ensure CHROMIUM_EXECUTABLE is set if it's empty
    CHROMIUM_PATH="$(command -v chromium-browser 2>/dev/null || command -v chromium 2>/dev/null || echo '')"
    if [[ -n "$CHROMIUM_PATH" ]] && grep -q "^CHROMIUM_EXECUTABLE=$" "$ENV_FILE"; then
        sed -i "s|^CHROMIUM_EXECUTABLE=.*|CHROMIUM_EXECUTABLE=$CHROMIUM_PATH|" "$ENV_FILE"
        echo "    Updated CHROMIUM_EXECUTABLE=$CHROMIUM_PATH in existing .env"
    fi
fi

# Ensure data/ directory exists for logs and DB
mkdir -p "$REPO_DIR/data/raw/prices"

# ---------------------------------------------------------------------------
# 6. Cron job (optional)
# ---------------------------------------------------------------------------
echo "[6/6] Cron job setup..."
echo ""
echo "Proposed cron schedule: Mo–Fr at 09:00, 12:00, 15:00, 18:00 (local time)"
echo "Command: $CRON_CMD"
echo ""
read -r -p "Install cron job? [y/N] " answer
if [[ "${answer,,}" == "y" ]]; then
    CRON_LINE="$CRON_SCHEDULE $CRON_CMD"
    # Remove existing entry for this repo to avoid duplicates
    ( crontab -l 2>/dev/null | grep -v "$REPO_DIR" ; echo "$CRON_LINE" ) | crontab -
    echo "    Cron job installed. Current crontab:"
    crontab -l | grep "$REPO_DIR"
else
    echo "    Skipped. To add later, run:"
    echo "      crontab -e"
    echo "    And add:"
    echo "      $CRON_SCHEDULE $CRON_CMD"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit your credentials:  nano $ENV_FILE"
echo "     Set TWSCRAPE_ACCOUNTS with your X cookies (ct0 + auth_token)"
echo ""
echo "  2. Test a single run:"
echo "     source $VENV/bin/activate"
echo "     python -m src.scraping.main --discover-only --limit 5 --queries '\$TSLA lang:en'"
echo ""
echo "  3. Check the database:"
echo "     python -c \""
echo "     import sqlite3, pathlib"
echo "     db = pathlib.Path('data/webmining.db')"
echo "     if db.exists():"
echo "         c = sqlite3.connect(db)"
echo "         print('Tweets:', c.execute('SELECT COUNT(*) FROM tweets').fetchone()[0])"
echo "     \""
echo ""
echo "  4. Full run (discovery + 2h polling):"
echo "     python -m src.scraping.main --limit 50"
