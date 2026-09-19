"""Tests for the Twelvedata request window and secret redaction.

Regression: _fetch_td_historical sent start_date == end_date, which
Twelvedata rejects as an empty interval (HTTP 400). That silently disabled
the paid primary source entirely -- all 18,880 cached prices came from the
yfinance fallback. The follow-on bug was an exclusive end_date returning the
*previous* trading day's close.
"""
from unittest.mock import MagicMock, patch

from src.config import redact
from src.market.price_fetcher import _td_window, _fetch_td_historical


class TestWindow:
    def test_start_and_end_differ(self):
        start, end = _td_window("2026-08-05")
        assert start != end, "identical start/end is rejected by Twelvedata"

    def test_end_is_day_after_target(self):
        # end_date is exclusive: end=2026-08-05 returns rows up to 08-04 only.
        _, end = _td_window("2026-08-05")
        assert end == "2026-08-06"

    def test_window_spans_holidays(self):
        # Must reach back past a weekend plus a multi-day TASE holiday.
        start, _ = _td_window("2026-08-05")
        assert start == "2026-07-26"

    def test_malformed_date_does_not_raise(self):
        assert _td_window("not-a-date") == ("not-a-date", "not-a-date")


class TestRequestShape:
    @patch("src.market.price_fetcher.requests.get")
    def test_request_uses_a_range(self, mock_get):
        resp = MagicMock()
        resp.json.return_value = {"values": [{"datetime": "2026-08-05", "close": "487.46"}]}
        mock_get.return_value = resp

        price = _fetch_td_historical("MSFT", "US", None, "2026-08-05")

        params = mock_get.call_args.kwargs["params"]
        assert params["start_date"] != params["end_date"]
        assert params["end_date"] == "2026-08-06"
        assert price == 487.46

    @patch("src.market.price_fetcher.requests.get")
    def test_picks_target_date_not_earlier_row(self, mock_get):
        # Values come newest-first; the target date must win over the day before.
        resp = MagicMock()
        resp.json.return_value = {"values": [
            {"datetime": "2026-08-05", "close": "487.46"},
            {"datetime": "2026-08-04", "close": "492.81"},
        ]}
        mock_get.return_value = resp

        assert _fetch_td_historical("MSFT", "US", None, "2026-08-05") == 487.46

    @patch("src.market.price_fetcher.requests.get")
    def test_falls_back_to_prior_trading_day(self, mock_get):
        # A weekend/holiday target has no row of its own; the latest row
        # <= target is correct.
        resp = MagicMock()
        resp.json.return_value = {"values": [
            {"datetime": "2026-08-07", "close": "499.99"},
        ]}
        mock_get.return_value = resp

        assert _fetch_td_historical("MSFT", "US", None, "2026-08-08") == 499.99


class TestRedaction:
    def test_api_key_removed_from_error_text(self):
        from src.config import TWELVEDATA_API_KEY
        if not TWELVEDATA_API_KEY:
            return
        msg = f"400 Client Error for url: https://api.twelvedata.com/x?apikey={TWELVEDATA_API_KEY}"
        out = redact(msg)
        assert TWELVEDATA_API_KEY not in out
        assert "<redacted>" in out

    def test_redacts_unknown_secrets_by_param_name(self):
        out = redact("https://x/y?token=abc123&password=hunter2&symbol=MSFT")
        assert "abc123" not in out and "hunter2" not in out
        assert "symbol=MSFT" in out
