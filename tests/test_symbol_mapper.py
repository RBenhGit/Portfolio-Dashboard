"""Tests for src/market/symbol_mapper.py — option detection and expiry parsing."""
from datetime import date

import pytest

from src.market.symbol_mapper import is_option, parse_option_expiry


class TestIsOption:
    def test_8digit_starting_8(self):
        assert is_option("83972174") is True

    def test_8digit_starting_9(self):
        assert is_option("90001234") is True

    def test_hebrew_name_pattern(self):
        assert is_option("99999", "תP001440M212-35") is True

    def test_regular_tase_stock(self):
        assert is_option("445015") is False

    def test_us_ticker(self):
        assert is_option("AAPL") is False

    def test_7digit_not_option(self):
        assert is_option("8000123") is False  # only 7 digits


class TestParseOptionExpiry:
    def test_m407_july_2024(self):
        assert parse_option_expiry("תP001560M407-35") == date(2024, 7, 31)

    def test_m212_dec_2022(self):
        assert parse_option_expiry("תP001440M212-35") == date(2022, 12, 31)

    def test_m301_jan_2023(self):
        assert parse_option_expiry("תP001500M301-35") == date(2023, 1, 31)

    def test_m209_sep_2022(self):
        assert parse_option_expiry("תP001640M209-35") == date(2022, 9, 30)

    def test_no_match_us_ticker(self):
        assert parse_option_expiry("AAPL") is None

    def test_no_match_none(self):
        assert parse_option_expiry(None) is None

    def test_no_match_empty(self):
        assert parse_option_expiry("") is None

    def test_future_date_is_future(self):
        result = parse_option_expiry("תP001560M612-35")  # Dec 2026
        assert result is not None
        assert result > date.today()
