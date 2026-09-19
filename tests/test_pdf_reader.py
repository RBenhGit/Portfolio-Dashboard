"""Tests for src/input/pdf_reader.py — row clustering, column mapping,
currency normalization, hashing, and quarantine behavior.

Runs against the real sample PDF (Trans_Input/IBI__000093395_001810.pdf),
the only real fixture available for this parser (a hand-built synthetic PDF
would not exercise the actual character-overlap defects this module exists
to handle). Skips gracefully if the PDF or its .env password are missing
so this doesn't fail in an environment that lacks the real fixture.
"""
from pathlib import Path

import pandas as pd
import pytest
from dotenv import dotenv_values

from src.input.pdf_reader import (
    read_pdf,
    OUTPUT_COLUMNS,
    IN_SCOPE_PAGES,
    HOLDINGS_TABLE_TOP_RANGE,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Fetched reports land in pdf_archive/; fall back to the original location.
_PDF_CANDIDATES = [
    PROJECT_ROOT / "Trans_Input" / "pdf_archive" / "IBI__000093395_001810.pdf",
    PROJECT_ROOT / "Trans_Input" / "IBI__000093395_001810.pdf",
]
PDF_PATH = next((p for p in _PDF_CANDIDATES if p.exists()), _PDF_CANDIDATES[0])
_ENV = dotenv_values(PROJECT_ROOT / ".env")
PDF_PASSWORD = _ENV.get("IBI_PDF_PASSWORD")

pytestmark = pytest.mark.skipif(
    not PDF_PATH.exists() or not PDF_PASSWORD,
    reason="Real sample PDF or IBI_PDF_PASSWORD not available in this environment",
)


@pytest.fixture(scope="module")
def parsed():
    df, quarantine = read_pdf(PDF_PATH, password=PDF_PASSWORD)
    return df, quarantine


class TestReadPdfShape:
    def test_returns_tuple_of_dataframe_and_list(self, parsed):
        df, quarantine = parsed
        assert isinstance(df, pd.DataFrame)
        assert isinstance(quarantine, list)

    def test_output_columns_match_excel_reader_contract(self, parsed):
        df, _ = parsed
        assert list(df.columns) == OUTPUT_COLUMNS

    def test_dates_sorted_ascending(self, parsed):
        df, _ = parsed
        dates = list(df["date"])
        assert dates == sorted(dates)

    def test_clean_rows_nonempty(self, parsed):
        df, _ = parsed
        assert len(df) > 0

    def test_quarantine_is_rare(self, parsed):
        # Was "must be non-empty": the converter used to lose ~37% of rows to
        # cluster over-merging. Now a row is quarantined only when the PDF
        # genuinely does not state something (e.g. no transaction type
        # printed), so quarantine must stay a small fraction of the page.
        df, quarantine = parsed
        assert len(quarantine) <= max(1, len(df) // 10), (
            f"{len(quarantine)} quarantined of {len(df)} parsed -- "
            "a regression in row reconstruction"
        )


class TestQuarantineHygiene:
    def test_quarantine_rows_have_required_keys(self, parsed):
        _, quarantine = parsed
        for q in quarantine:
            assert "page" in q
            assert "top_range" in q
            assert "raw_chars" in q
            assert "reason" in q
            assert q["reason"]  # non-empty explanation

    def test_quarantine_rows_only_from_in_scope_pages(self, parsed):
        _, quarantine = parsed
        for q in quarantine:
            assert q["page"] in IN_SCOPE_PAGES

    def test_no_merged_or_guessed_fields_in_main_df(self, parsed):
        # A clean row must never carry evidence of a merged field. The PLTR
        # row that used to arrive as a garbled id ('24 15474 1') now parses
        # correctly, so the assertion is on the invariant, not on that row
        # still being broken.
        df, _ = parsed
        for sym in df["security_symbol"]:
            assert " " not in str(sym)
        for tx_type in df["transaction_type"]:
            assert tx_type, "empty transaction_type must be quarantined, not emitted"

    def test_no_nan_in_main_df(self, parsed):
        df, _ = parsed
        assert not df.isna().any().any()


class TestHandVerifiedRows:
    """Cross-checked by hand against page.chars coordinates and against
    Trans_Input/Transactions_IBI_Q1_2026.xlsx's column conventions for the
    same account (see pdf_reader.py's module docstring for the derivation).
    """

    def test_tax_withdrawal_row_06_07_26(self, parsed):
        df, _ = parsed
        row = df[(df["date"] == "2026-07-06") & (df["security_symbol"] == "9993983")]
        assert len(row) == 1
        r = row.iloc[0]
        # Phantom tax row: 'quantity' column here carries the NIS tax
        # amount (matches Excel's own convention for this row type, where
        # the qty column holds a monetary figure, not a share count).
        assert r["quantity"] == pytest.approx(-1.51)
        assert r["currency"] == "₪"
        assert r["commission"] == pytest.approx(0.0)

    def test_msft_buy_row_14_07_26(self, parsed):
        df, _ = parsed
        row = df[(df["date"] == "2026-07-14") & (df["security_symbol"] == "MSFT")]
        assert len(row) == 1
        r = row.iloc[0]
        # This row prints NO security name in the PDF (the name column is
        # empty), so the ticker comes from _KNOWN_US_NUMERIC_IDS via the id
        # 105049 rather than from the name. Identified by matching this
        # row's date/price/quantity against the Excel history, where the
        # same trade appears as MSFT 2026-07-14 -2 @ 388.00.
        assert r["currency"] == "$"
        assert r["quantity"] == pytest.approx(-2.00)
        # Price is de-scaled from the PDF's raw '38,800.00' (x100 display
        # quirk for USD rows) to match Excel's plain-dollar convention.
        assert r["execution_price_raw"] == pytest.approx(388.00)
        assert r["commission"] == pytest.approx(7.53)
        # quantity * price reproduces the PDF's own verification footnote
        # ('776.00 USD ....חטמב יוכיז' directly below this row).
        assert abs(r["amount_foreign_currency"]) == pytest.approx(776.00)

    def test_fx_purchase_row_99028(self, parsed):
        df, _ = parsed
        row = df[(df["date"] == "2026-07-13") & (df["security_symbol"] == "99028")
                  & (df["amount_local_currency"] < 0)]
        assert len(row) == 1
        r = row.iloc[0]
        # USD bought at an agorot/USD rate; qty * rate/100 ~= |amount_nis|
        # (net of the row's own commission, here 0).
        computed = r["quantity"] * r["execution_price_raw"] / 100.0
        assert computed == pytest.approx(abs(r["amount_local_currency"]), abs=0.01)

    def test_nesuah_vision_ils_row(self, parsed):
        df, _ = parsed
        row = df[(df["date"] == "2026-07-13") & (df["security_symbol"] == "1176593")]
        assert len(row) == 1
        r = row.iloc[0]
        assert r["currency"] == "₪"
        assert r["commission"] == pytest.approx(2.35)
        # execution_price_raw stays raw agorot for ILS rows (no /100 -- the
        # PDF's ILS price column already matches Excel's raw-agorot
        # convention directly).
        assert r["execution_price_raw"] == pytest.approx(23060.00)


class TestUsTickerExtraction:
    """detect_market() in symbol_mapper.py treats a purely-numeric symbol
    as TASE unless it's in _KNOWN_US_NUMERIC_IDS, but the PDF always prints
    IBI's internal numeric id (never a ticker) for every security,
    including genuine US stocks. Confirmed against real Excel data
    (Trans_Input/Transactions_IBI.xlsx) that Excel's own security_symbol
    column already uses the plain ticker for these same securities -- so
    this module must derive it from the name, matching Excel's convention,
    or every USD row misclassifies as TASE."""

    def test_all_usd_rows_get_ticker_not_numeric_id(self, parsed):
        df, _ = parsed
        usd_rows = df[df["currency"] == "$"]
        assert len(usd_rows) > 0
        for sym in usd_rows["security_symbol"]:
            assert not sym.isdigit(), f"USD row kept numeric id {sym!r} instead of a ticker"

    def test_name_paren_pattern_extracts_ticker(self, parsed):
        # "MICROSOFT(MSFT)" -> "MSFT"
        df, _ = parsed
        row = df[df["security_symbol"] == "MSFT"]
        assert len(row) == 1

    def test_ticker_us_pattern_extracts_ticker(self, parsed):
        # "GOOG US" -> "GOOG"
        df, _ = parsed
        row = df[df["security_symbol"] == "GOOG"]
        assert len(row) == 1

    def test_leading_ticker_pattern_extracts_ticker(self, parsed):
        # "AMZN <hebrew name>" -> "AMZN"
        df, _ = parsed
        row = df[df["security_symbol"] == "AMZN"]
        assert len(row) == 1

    def test_ils_rows_keep_numeric_id_unchanged(self, parsed):
        # TASE rows must NOT get ticker-extracted -- they're genuinely
        # numeric-id-only in both the PDF and Excel.
        df, _ = parsed
        ils_rows = df[df["currency"] == "₪"]
        numeric_ones = [s for s in ils_rows["security_symbol"] if str(s).isdigit()]
        assert len(numeric_ones) > 0


class TestCurrencyNormalization:
    def test_currency_values_are_symbols_not_codes(self, parsed):
        df, _ = parsed
        # normalize_price()/detect_market() check for the exact symbols
        # '₪' and '$', not the PDF's 3-letter codes.
        assert set(df["currency"].unique()) <= {"₪", "$"}
        assert "USD" not in set(df["currency"].unique())
        assert "ILS" not in set(df["currency"].unique())

    def test_usd_row_maps_to_dollar_sign(self, parsed):
        df, _ = parsed
        usd_rows = df[df["security_symbol"] == "MSFT"]
        assert len(usd_rows) == 1
        assert usd_rows.iloc[0]["currency"] == "$"

    def test_ils_row_maps_to_shekel_sign(self, parsed):
        df, _ = parsed
        ils_rows = df[df["security_symbol"] == "1176593"]  # Nesuah Vision
        assert len(ils_rows) == 1
        assert ils_rows.iloc[0]["currency"] == "₪"

    def test_blank_currency_defaults_to_shekel(self, parsed):
        df, _ = parsed
        # Phantom/transfer rows (e.g. id '900') print no currency word in
        # the PDF; matches Excel's own convention of '₪' for these types.
        phantom_rows = df[df["security_symbol"] == "900"]
        assert len(phantom_rows) > 0
        assert (phantom_rows["currency"] == "₪").all()


class TestRowHash:
    def test_row_hash_is_sha256_hex(self, parsed):
        df, _ = parsed
        for h in df["row_hash"]:
            assert len(h) == 64
            int(h, 16)  # raises if not hex

    def test_row_hash_unique_per_row(self, parsed):
        df, _ = parsed
        assert df["row_hash"].nunique() == len(df)

    def test_row_hash_stable_across_reads(self):
        first, _ = read_pdf(PDF_PATH, password=PDF_PASSWORD)
        second, _ = read_pdf(PDF_PATH, password=PDF_PASSWORD)
        assert list(first["row_hash"]) == list(second["row_hash"])


class TestKnownGapsDefaultToZero:
    def test_additional_fees_defaults_to_zero(self, parsed):
        df, _ = parsed
        assert (df["additional_fees"] == 0.0).all()

    def test_capital_gains_tax_estimate_defaults_to_zero(self, parsed):
        df, _ = parsed
        assert (df["capital_gains_tax_estimate"] == 0.0).all()

    def test_balance_defaults_to_zero(self, parsed):
        # The PDF's daily transaction log doesn't print a running balance
        # column comparable to Excel's 'יתרה שקלית'.
        df, _ = parsed
        assert (df["balance"] == 0.0).all()


class TestOutOfScopeHoldingsTableExcluded:
    def test_holdings_table_percentage_rows_not_in_output(self, parsed):
        # The bleed-through holdings table's rows start with a
        # percentage-like number under 100 (e.g. '13.09', '5.81') and never
        # satisfy the DD/MM/YY date-at-x0~24.8 check, so they must never
        # appear as a parsed transaction's date.
        df, _ = parsed
        for d in df["date"]:
            # every parsed date must be a real calendar date string
            pd.Timestamp(d)  # raises if not parseable as a date

    def test_no_output_row_has_holdings_table_security_ids(self, parsed):
        # INTEL/GAP/NVIDIA/ALIBABA appear only in the holdings-table
        # bleed-through in the observed HOLDINGS_TABLE_TOP_RANGE region on
        # the sample PDF, using a different column grid than the
        # transaction log; none of that should surface as a clean parsed
        # transaction row (it's either excluded outright as non-primary or
        # would fail validation and land in quarantine, never in df).
        df, _ = parsed
        names_and_ids = " ".join(df["security_name"]) + " " + " ".join(df["security_symbol"])
        for holdings_only_id in ("104794", "112367"):  # INTEL, GAP INC ids seen only in the bleed-through block
            assert holdings_only_id not in names_and_ids

    def test_holdings_table_top_range_documented(self):
        # Sanity check on the documented constant itself.
        lo, hi = HOLDINGS_TABLE_TOP_RANGE
        assert lo < hi
