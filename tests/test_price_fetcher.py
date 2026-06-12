"""Tests for src/market/price_fetcher.py — agorot normalization + cache/option guards."""
from unittest.mock import patch, MagicMock

import pytest

from src.market.price_fetcher import _normalize_tase, get_price


# ---------------------------------------------------------------------------
# _normalize_tase — the agorot → shekel conversion heuristics
# ---------------------------------------------------------------------------

class TestNormalizeTase:
    def test_us_price_unchanged_twelvedata(self):
        assert _normalize_tase(250.5, "US", "twelvedata") == 250.5

    def test_us_price_unchanged_even_above_threshold(self):
        # BRK.A-style prices must never be divided
        assert _normalize_tase(620_000.0, "US", "yfinance") == 620_000.0

    def test_yfinance_tase_always_divides_by_100(self):
        # yfinance .TA quotes are always in ILA (agorot)
        assert _normalize_tase(17_000.0, "TASE", "yfinance") == pytest.approx(170.0)

    def test_yfinance_tase_divides_even_small_values(self):
        # Penny stock at 95 agorot → ₪0.95 (no threshold for yfinance)
        assert _normalize_tase(95.0, "TASE", "yfinance") == pytest.approx(0.95)

    def test_twelvedata_tase_above_threshold_divided(self):
        assert _normalize_tase(17_000.0, "TASE", "twelvedata") == pytest.approx(170.0)

    def test_twelvedata_tase_below_threshold_unchanged(self):
        # Already in shekels — must not be divided again
        assert _normalize_tase(170.0, "TASE", "twelvedata") == pytest.approx(170.0)

    def test_twelvedata_tase_exact_threshold_unchanged(self):
        # Heuristic is strictly greater-than 10,000
        assert _normalize_tase(10_000.0, "TASE", "twelvedata") == pytest.approx(10_000.0)

    def test_unknown_source_uses_heuristic(self):
        assert _normalize_tase(45_000.0, "TASE", "manual") == pytest.approx(450.0)
        assert _normalize_tase(450.0, "TASE", "manual") == pytest.approx(450.0)


# ---------------------------------------------------------------------------
# get_price — option guard and cache short-circuit
# ---------------------------------------------------------------------------

class TestGetPrice:
    @patch("src.market.price_fetcher.repository")
    def test_option_by_symbol_returns_none_without_db(self, mock_repo):
        # 8-digit ID starting with 8/9 is an option — non-priceable
        assert get_price("81234567", "TASE", None, "2024-01-02") is None
        mock_repo.get_cached_price.assert_not_called()

    @patch("src.market.price_fetcher.repository")
    def test_option_by_name_returns_none_without_db(self, mock_repo):
        assert get_price("12345", "TASE", "תP001560M407-35", "2024-01-02") is None
        mock_repo.get_cached_price.assert_not_called()

    @patch("src.market.price_fetcher._fetch_historical")
    @patch("src.market.price_fetcher.repository")
    def test_cached_price_skips_fetch(self, mock_repo, mock_fetch):
        mock_repo.get_cached_price.return_value = 123.45
        assert get_price("AAPL", "US", "Apple", "2024-01-02") == 123.45
        mock_fetch.assert_not_called()

    @patch("src.market.price_fetcher._fetch_historical")
    @patch("src.market.price_fetcher.repository")
    def test_fetched_price_is_cached(self, mock_repo, mock_fetch):
        mock_repo.get_cached_price.return_value = None
        mock_fetch.return_value = 50.0
        assert get_price("AAPL", "US", "Apple", "2024-01-02") == 50.0
        mock_repo.upsert_price.assert_called_once()
        args = mock_repo.upsert_price.call_args[0]
        assert args[0] == "AAPL"
        assert args[2] == 50.0

    @patch("src.market.price_fetcher._fetch_historical")
    @patch("src.market.price_fetcher.repository")
    def test_failed_fetch_not_cached(self, mock_repo, mock_fetch):
        mock_repo.get_cached_price.return_value = None
        mock_fetch.return_value = None
        assert get_price("AAPL", "US", "Apple", "2024-01-02") is None
        mock_repo.upsert_price.assert_not_called()
