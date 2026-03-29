"""Tests for src.finance.price_fetcher."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.finance.price_fetcher import (
    COLUMN_ORDER,
    fetch_and_save,
    fetch_prices,
    save_prices,
)


@pytest.fixture()
def sample_yf_dataframe() -> pd.DataFrame:
    """Mimics the DataFrame returned by ``yf.download`` for a single ticker."""
    dates = pd.date_range("2024-06-01", periods=5, freq="B", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [150.0, 151.0, 152.0, 153.0, 154.0],
            "High": [155.0, 156.0, 157.0, 158.0, 159.0],
            "Low": [149.0, 150.0, 151.0, 152.0, 153.0],
            "Close": [153.0, 154.0, 155.0, 156.0, 157.0],
            "Adj Close": [153.0, 154.0, 155.0, 156.0, 157.0],
            "Volume": [1_000_000] * 5,
        },
        index=dates,
    )
    df.index.name = "Date"
    return df


@patch("src.finance.price_fetcher._load_existing")
@patch("src.finance.price_fetcher.time.sleep")
@patch("src.finance.price_fetcher.yf.download")
class TestFetchPrices:
    def test_returns_tidy_dataframe(
        self,
        mock_download: MagicMock,
        _mock_sleep: MagicMock,
        mock_load: MagicMock,
        sample_yf_dataframe: pd.DataFrame,
    ) -> None:
        mock_download.return_value = sample_yf_dataframe
        mock_load.return_value = pd.DataFrame(columns=COLUMN_ORDER)

        df = fetch_prices(tickers=["AAPL"], start="2024-06-01", end="2024-06-08")

        assert not df.empty
        assert "Date" in df.columns
        assert "Ticker" in df.columns
        assert (df["Ticker"] == "AAPL").all()
        assert set(df.columns) >= {"Open", "High", "Low", "Close", "Volume"}

    def test_handles_empty_response(
        self, mock_download: MagicMock, _mock_sleep: MagicMock, mock_load: MagicMock,
    ) -> None:
        mock_download.return_value = pd.DataFrame()
        mock_load.return_value = pd.DataFrame(columns=COLUMN_ORDER)

        df = fetch_prices(tickers=["INVALID"], start="2024-06-01", end="2024-06-08")

        assert df.empty

    def test_handles_download_exception(
        self, mock_download: MagicMock, _mock_sleep: MagicMock, mock_load: MagicMock,
    ) -> None:
        mock_download.side_effect = Exception("network error")
        mock_load.return_value = pd.DataFrame(columns=COLUMN_ORDER)

        df = fetch_prices(tickers=["AAPL"], start="2024-06-01", end="2024-06-08")

        assert df.empty

    def test_multiple_tickers(
        self,
        mock_download: MagicMock,
        _mock_sleep: MagicMock,
        mock_load: MagicMock,
        sample_yf_dataframe: pd.DataFrame,
    ) -> None:
        mock_download.return_value = sample_yf_dataframe
        mock_load.return_value = pd.DataFrame(columns=COLUMN_ORDER)

        df = fetch_prices(
            tickers=["AAPL", "MSFT"], start="2024-06-01", end="2024-06-08"
        )

        assert set(df["Ticker"].unique()) == {"AAPL", "MSFT"}
        assert len(df) == 10  # 5 rows × 2 tickers

    def test_incremental_skips_up_to_date_ticker(
        self,
        mock_download: MagicMock,
        _mock_sleep: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """When existing data already covers the end date, skip fetching."""
        existing = pd.DataFrame(
            {"Date": ["2024-06-07"], "Ticker": ["AAPL"], "Open": [150.0],
             "High": [155.0], "Low": [149.0], "Close": [153.0],
             "Adj Close": [153.0], "Volume": [1_000_000]}
        )
        mock_load.return_value = existing

        df = fetch_prices(tickers=["AAPL"], end="2024-06-07")

        mock_download.assert_not_called()
        assert df.empty


class TestSavePrices:
    def test_writes_csv_and_meta(self, tmp_path: Path) -> None:
        df = pd.DataFrame(
            {
                "Date": ["2024-06-03", "2024-06-04"],
                "Ticker": ["AAPL", "AAPL"],
                "Open": [150.0, 151.0],
                "High": [155.0, 156.0],
                "Low": [149.0, 150.0],
                "Close": [153.0, 154.0],
                "Adj Close": [153.0, 154.0],
                "Volume": [1_000_000, 1_100_000],
            }
        )

        csv = tmp_path / "prices.csv"
        meta = tmp_path / "prices_meta.json"

        with (
            patch("src.finance.price_fetcher.RAW_PRICES_DIR", tmp_path),
            patch("src.finance.price_fetcher.PRICES_CSV", csv),
            patch("src.finance.price_fetcher.PRICES_META", meta),
        ):
            path = save_prices(df)

        assert path.exists()
        assert path.suffix == ".csv"
        assert meta.exists()

        reloaded = pd.read_csv(path)
        assert len(reloaded) == 2

    def test_deduplicates_on_merge(self, tmp_path: Path) -> None:
        """Saving overlapping data should not create duplicate rows."""
        existing = pd.DataFrame(
            {
                "Date": ["2024-06-03"],
                "Ticker": ["AAPL"],
                "Open": [150.0], "High": [155.0], "Low": [149.0],
                "Close": [153.0], "Adj Close": [153.0], "Volume": [1_000_000],
            }
        )
        csv = tmp_path / "prices.csv"
        meta = tmp_path / "prices_meta.json"
        existing.to_csv(csv, index=False)

        new_df = pd.DataFrame(
            {
                "Date": ["2024-06-03", "2024-06-04"],
                "Ticker": ["AAPL", "AAPL"],
                "Open": [150.5, 151.0], "High": [155.0, 156.0], "Low": [149.0, 150.0],
                "Close": [153.0, 154.0], "Adj Close": [153.0, 154.0],
                "Volume": [1_000_000, 1_100_000],
            }
        )

        with (
            patch("src.finance.price_fetcher.RAW_PRICES_DIR", tmp_path),
            patch("src.finance.price_fetcher.PRICES_CSV", csv),
            patch("src.finance.price_fetcher.PRICES_META", meta),
        ):
            save_prices(new_df)

        result = pd.read_csv(csv)
        assert len(result) == 2  # not 3


class TestFetchAndSave:
    @patch("src.finance.price_fetcher.save_prices")
    @patch("src.finance.price_fetcher.fetch_prices")
    def test_returns_none_when_no_data_and_no_file(
        self, mock_fetch: MagicMock, mock_save: MagicMock
    ) -> None:
        mock_fetch.return_value = pd.DataFrame(columns=COLUMN_ORDER)

        with patch("src.finance.price_fetcher.PRICES_CSV", Path("/nonexistent/prices.csv")):
            result = fetch_and_save(tickers=["AAPL"])

        assert result is None
        mock_save.assert_not_called()
