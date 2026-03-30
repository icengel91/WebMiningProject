"""Tests for the X crawler logic (mocked — no real API calls)."""

import pytest

from src.scraping.x_crawler import extract_cashtag


class TestExtractCashtag:
    def test_single_cashtag(self):
        assert extract_cashtag("Just bought $TSLA, to the moon!") == "TSLA"

    def test_multiple_returns_first(self):
        assert extract_cashtag("$AAPL vs $MSFT — who wins?") == "AAPL"

    def test_no_cashtag(self):
        assert extract_cashtag("Stocks are crashing again") is None

    def test_lowercase_ignored(self):
        # Only uppercase cashtags are recognised
        assert extract_cashtag("Look at $tsla") is None

    def test_dollar_amount_not_matched(self):
        assert extract_cashtag("I made $500 today") is None

    def test_cashtag_at_start(self):
        assert extract_cashtag("$SAP is undervalued") == "SAP"

    def test_cashtag_at_end(self):
        assert extract_cashtag("Everyone should buy $NVDA") == "NVDA"
