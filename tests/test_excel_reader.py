"""Tests for src/input/excel_reader.py — header mapping, date parsing, hashing."""
import pandas as pd
import pytest

from src.input.excel_reader import read_excel, iter_rows, COLUMN_MAP

# All Hebrew headers from a real IBI export, in IBI's column order
_HEBREW_COLS = [
    "תאריך", "סוג פעולה", "שם נייר", "מס' נייר / סימבול", "כמות",
    "שער ביצוע", "מטבע", "עמלת פעולה", "עמלות נלוות",
    'תמורה במט"ח', "תמורה בשקלים", "יתרה שקלית", "אומדן מס רווחי הון",
]


def _row(date="02/01/2024", tx_type="קניה שח", name="מטריקס", symbol="445015",
         qty="10", price="17000", currency="₪", commission="5", fees="0",
         amount_fx="0", amount_nis="-1700", balance="8300", tax="0"):
    return [date, tx_type, name, symbol, qty, price, currency,
            commission, fees, amount_fx, amount_nis, balance, tax]


def _make_excel(path, rows):
    df = pd.DataFrame(rows, columns=_HEBREW_COLS)
    df.to_excel(str(path), index=False, engine="openpyxl")
    return path


@pytest.fixture
def sample_xlsx(tmp_path):
    # IBI exports newest-first — write out of order to exercise the sort
    return _make_excel(tmp_path / "ibi.xlsx", [
        _row(date="03/01/2024", tx_type="מכירה שח", qty="5", price="20000",
             amount_nis="1000", balance="9300"),
        _row(date="02/01/2024"),
    ])


class TestReadExcel:
    def test_hebrew_columns_renamed(self, sample_xlsx):
        df = read_excel(sample_xlsx)
        for english in COLUMN_MAP.values():
            assert english in df.columns

    def test_dates_parsed_ddmmyyyy_and_sorted_asc(self, sample_xlsx):
        df = read_excel(sample_xlsx)
        assert list(df["date"]) == ["2024-01-02", "2024-01-03"]

    def test_invalid_date_rows_dropped(self, tmp_path):
        path = _make_excel(tmp_path / "bad.xlsx", [
            _row(date="02/01/2024"),
            _row(date="not-a-date"),
        ])
        df = read_excel(path)
        assert len(df) == 1

    def test_row_hash_is_sha256_hex(self, sample_xlsx):
        df = read_excel(sample_xlsx)
        for h in df["row_hash"]:
            assert len(h) == 64
            int(h, 16)  # raises if not hex

    def test_row_hash_unique_per_distinct_row(self, sample_xlsx):
        df = read_excel(sample_xlsx)
        assert df["row_hash"].nunique() == len(df)

    def test_row_hash_stable_across_reads(self, sample_xlsx):
        first = list(read_excel(sample_xlsx)["row_hash"])
        second = list(read_excel(sample_xlsx)["row_hash"])
        assert first == second

    def test_numeric_columns_converted(self, sample_xlsx):
        df = read_excel(sample_xlsx)
        assert df["quantity"].iloc[0] == pytest.approx(10.0)
        assert df["execution_price_raw"].iloc[0] == pytest.approx(17000.0)
        assert df["amount_local_currency"].iloc[0] == pytest.approx(-1700.0)

    def test_blank_numeric_becomes_zero(self, tmp_path):
        path = _make_excel(tmp_path / "blank.xlsx", [_row(commission="")])
        df = read_excel(path)
        assert df["commission"].iloc[0] == 0.0

    def test_currency_and_symbol_stripped(self, tmp_path):
        path = _make_excel(tmp_path / "ws.xlsx", [_row(currency=" ₪ ", symbol=" 445015 ")])
        df = read_excel(path)
        assert df["currency"].iloc[0] == "₪"
        assert df["security_symbol"].iloc[0] == "445015"


class TestIterRows:
    def test_yields_dicts(self, sample_xlsx):
        df = read_excel(sample_xlsx)
        rows = list(iter_rows(df))
        assert len(rows) == 2
        assert all(isinstance(r, dict) for r in rows)
        assert rows[0]["security_symbol"] == "445015"
