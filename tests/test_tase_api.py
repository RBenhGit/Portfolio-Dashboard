"""Tests for src/market/tase_api.py — TASE website API lookup and parsing."""
from unittest.mock import MagicMock, patch

from src.market.symbol_mapper import _yf_from_td
from src.market.tase_api import _display_name, lookup_security


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class TestLookupSecurity:
    @patch("src.market.tase_api.requests.get")
    def test_resolves_symbol_and_name(self, mock_get):
        mock_get.return_value = _mock_response({
            "Symbol": "MPP",
            "CompanyName": "MORE PENSION",
            "SecurityLongName": "MORE PROVIDENT FUNDS AND PENSION LTD",
        })
        assert lookup_security("1184381") == {"symbol": "MPP", "name": "More Pension"}
        params = mock_get.call_args.kwargs["params"]
        assert params == {"securityId": "1184381", "lang": "1"}

    @patch("src.market.tase_api.requests.get")
    def test_unknown_id_null_body(self, mock_get):
        mock_get.return_value = _mock_response(None)
        assert lookup_security("99999999") is None

    @patch("src.market.tase_api.requests.get")
    def test_missing_symbol_returns_none(self, mock_get):
        mock_get.return_value = _mock_response({"CompanyName": "SOMETHING", "Symbol": ""})
        assert lookup_security("1184381") is None

    @patch("src.market.tase_api.requests.get")
    def test_http_error_returns_none(self, mock_get):
        mock_get.side_effect = Exception("network down")
        assert lookup_security("445015") is None

    @patch("src.market.tase_api.requests.get")
    def test_name_falls_back_to_symbol(self, mock_get):
        mock_get.return_value = _mock_response({"Symbol": "MTRX"})
        assert lookup_security("445015") == {"symbol": "MTRX", "name": "MTRX"}

    @patch("src.market.tase_api.requests.get")
    def test_id_is_stripped(self, mock_get):
        mock_get.return_value = _mock_response({"Symbol": "MTRX", "CompanyName": "MATRIX"})
        lookup_security(" 445015 ")
        assert mock_get.call_args.kwargs["params"]["securityId"] == "445015"


class TestDisplayName:
    def test_all_caps_title_cased(self):
        assert _display_name({"CompanyName": "MORE PENSION"}) == "More Pension"

    def test_mixed_case_kept(self):
        assert _display_name({"CompanyName": "Matrix IT"}) == "Matrix IT"

    def test_falls_back_to_long_name(self):
        assert _display_name({"SecurityLongName": "MATRIX IT LTD."}) == "Matrix It Ltd."

    def test_empty(self):
        assert _display_name({}) == ""


class TestYfFromTd:
    def test_plain_ticker(self):
        assert _yf_from_td("MTRX") == "MTRX.TA"

    def test_dotted_ticker(self):
        assert _yf_from_td("TCH.F139") == "TCH-F139.TA"
