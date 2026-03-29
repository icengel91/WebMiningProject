"""Scheduler that fetches stock prices three times per day.

Usage:
    python -m src.finance.scheduler            # foreground (Ctrl-C to stop)
    python -m src.finance.scheduler --once      # single run then exit

The three daily runs default to 09:30, 13:00, and 17:00 UTC.
Adjust ``SCHEDULE_TIMES_UTC`` to change.
"""

import argparse
import logging
import signal
import sys
import time

import schedule

from src.finance.price_fetcher import fetch_and_save

logger = logging.getLogger(__name__)

# Three daily run times (UTC, HH:MM) — roughly market open, midday, and close
SCHEDULE_TIMES_UTC: list[str] = ["09:30", "13:00", "17:00"]


def _run_job() -> None:
    """Execute a single incremental fetch-and-save run."""
    logger.info("Scheduled run started.")
    try:
        path = fetch_and_save()
        if path:
            logger.info("Run complete — %s", path)
        else:
            logger.warning("Run complete — no data fetched.")
    except Exception:
        logger.error("Scheduled run failed.", exc_info=True)


def build_schedule() -> None:
    """Register the three daily jobs with the ``schedule`` library."""
    for time_str in SCHEDULE_TIMES_UTC:
        schedule.every().day.at(time_str, "UTC").do(_run_job)
        logger.info("Scheduled daily run at %s UTC.", time_str)


def run_forever() -> None:
    """Block and execute pending jobs in a loop until interrupted."""
    stop = False

    def _handle_signal(signum: int, _frame: object) -> None:
        nonlocal stop
        logger.info("Received signal %d — shutting down.", signum)
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Scheduler running. Next job at %s. Press Ctrl-C to stop.",
        schedule.next_run(),
    )

    while not stop:
        schedule.run_pending()
        time.sleep(30)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(description="Stock-price scheduler (3× daily)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single fetch immediately and exit (useful for testing).",
    )
    args = parser.parse_args()

    if args.once:
        _run_job()
        sys.exit(0)

    build_schedule()
    run_forever()


if __name__ == "__main__":
    main()
