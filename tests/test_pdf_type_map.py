"""Tests for src/input/pdf_type_map.py — PDF abbreviation -> Excel type
string translation, and the end-to-end guarantee that IBIClassifier can
actually classify translated PDF rows (not just that the mapping table
looks plausible)."""
from pathlib import Path

import pytest
from dotenv import dotenv_values

from src.input.pdf_type_map import (
    CLASSIFIER_VOCABULARY,
    UnknownTransactionType,
    translate_tx_type,
)
from src.classifiers.ibi_classifier import IBIClassifier

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Fetched reports land in pdf_archive/; fall back to the original location so
# the tests run wherever the sample happens to be.
_PDF_CANDIDATES = [
    PROJECT_ROOT / "Trans_Input" / "pdf_archive" / "IBI__000093395_001810.pdf",
    PROJECT_ROOT / "Trans_Input" / "IBI__000093395_001810.pdf",
]
PDF_PATH = next((p for p in _PDF_CANDIDATES if p.exists()), _PDF_CANDIDATES[0])
_ENV = dotenv_values(PROJECT_ROOT / ".env")
PDF_PASSWORD = _ENV.get("IBI_PDF_PASSWORD")


class TestTranslateTxType:
    def test_known_abbreviations_translate(self):
        assert translate_tx_type('ל"וח/מ') == "מכירה חול מטח"
        assert translate_tx_type('ל"וח/ק') == "קניה חול מטח"
        assert translate_tx_type("ףיצר/מ") == "מכירה רצף"
        assert translate_tx_type("ףיצר/ק") == "קניה רצף"
        assert translate_tx_type("הרבעה") == "העברה מזומן בשח"
        assert translate_tx_type("הינק") == "קניה שח"

    def test_unrecognized_type_raises(self):
        # An untranslatable type must NOT pass through: the classifier has no
        # `else` branch, so it would be inserted with effect="none" -- in the
        # DB but invisible to the builder. Raising lets the reader quarantine
        # the row instead.
        with pytest.raises(UnknownTransactionType):
            translate_tx_type("XYZ_UNKNOWN")

    def test_empty_type_raises(self):
        with pytest.raises(UnknownTransactionType):
            translate_tx_type("")

    def test_error_reports_readable_hebrew(self):
        # The raw PDF string is reversed, so the reason must show the
        # un-reversed form or it is unreadable in a quarantine report.
        with pytest.raises(UnknownTransactionType) as exc:
            translate_tx_type("דנדביד_XX")
        assert exc.value.readable == "דנדביד_XX"[::-1]

    def test_all_translated_values_are_real_excel_types(self):
        # Every mapping target must be one of IBIClassifier's 21 known
        # Excel-vocabulary strings, or classify() will silently no-op it —
        # exactly the bug this module exists to prevent.
        from src.input.pdf_type_map import _ABBREV_MAP, _AMBIGUOUS_MAP

        for pdf_abbrev, excel_type in _ABBREV_MAP.items():
            assert excel_type in CLASSIFIER_VOCABULARY, (
                f"{pdf_abbrev!r} maps to {excel_type!r}, which is not a "
                "recognized IBIClassifier tx_type"
            )
        for pdf_abbrev, rule in _AMBIGUOUS_MAP.items():
            targets = [t for _, t in rule["by_name"]] + [rule["default"]]
            for excel_type in targets:
                assert excel_type in CLASSIFIER_VOCABULARY, (
                    f"{pdf_abbrev!r} can map to {excel_type!r}, which is not "
                    "a recognized IBIClassifier tx_type"
                )

    def test_option_and_dividend_types_translate(self):
        # Previously missing entries: an option write and a TASE dividend
        # both landed in the DB as effect='none'.
        assert translate_tx_type("ףועמ/מ") == "מכירה מעוף"
        assert translate_tx_type("דנדביד") == "דיבדנד"

    def test_ambiguous_type_disambiguated_by_security_name(self):
        # 'מכירה' means a forex sell for the USD wrapper but a tax row
        # otherwise -- a single lookup would conflate two different
        # transactions. security_name arrives reversed, as from the PDF.
        forex = translate_tx_type("הריכמ", "99028", 'ב"הרא רלוד')
        tax = translate_tx_type("הריכמ", "9993975", "םילובקת סמ")
        assert forex == "מכירה חול מטח"
        assert tax == "משיכת מס מטח"


@pytest.mark.skipif(
    not PDF_PATH.exists() or not PDF_PASSWORD,
    reason="Real sample PDF or IBI_PDF_PASSWORD not available in this environment",
)
class TestEndToEndClassification:
    """The real regression test: every clean row the PDF parser produces
    must be classifiable (effect != 'none'), proving the translation layer
    actually closes the gap end-to-end rather than just looking right in
    isolation."""

    def test_no_clean_pdf_row_classifies_as_none(self):
        # Two pre-existing, PDF-independent gaps are tolerated here: a
        # phantom row whose tx_type is "קניה שח" (999*-prefixed tax-paid
        # symbol) or "הפקדה" (symbol 5039813, name "הכנס/תשלום מעוף")
        # classifies as effect="none" in IBIClassifier today even when
        # sourced from Excel directly -- confirmed by feeding the exact
        # same (tx_type, symbol, name) combinations from real Excel data
        # through IBIClassifier.classify() in isolation (both branches
        # require `not is_phantom`, and these rows are phantom by
        # symbol/name match). These are existing IBIClassifier
        # limitations, not something the PDF translation layer introduced
        # or should silently paper over.
        from src.input.pdf_reader import read_pdf

        df, _ = read_pdf(PDF_PATH, password=PDF_PASSWORD)
        classifier = IBIClassifier()
        unclassified = []
        for _, row in df.iterrows():
            result = classifier.classify(row.to_dict())
            if result["effect"] == "none":
                unclassified.append((row["date"], row["transaction_type"], row["security_symbol"]))

        # Phantom tax/settlement rows: IBIClassifier's branches for these
        # types all require `not is_phantom`, so they intentionally produce
        # effect="none" and are counted for cash only. Verified against the
        # live DB, where the identical (type, symbol) pairs arrive from
        # Excel with effect='none' and is_phantom=1 -- e.g. ("הפקדה",
        # "9992985") appears 58 times. Not a translation-layer gap.
        known_preexisting_gaps = {
            ("קניה שח", "9993983"),
            ("הפקדה", "5039813"),
            ("הפקדה", "9992985"),
            ("הפקדה", "9993983"),
            ("הפקדה", "9993975"),
        }
        unexpected = [r for r in unclassified if (r[1], str(r[2])) not in known_preexisting_gaps]
        assert not unexpected, f"Rows still classify as effect=none: {unexpected}"

    def test_us_sell_classifies_as_sell_on_us_market(self):
        # Any USD sell must classify as a US-market sell. Uses whichever US
        # ticker the sample PDF happens to contain rather than a hardcoded
        # symbol, which silently made this test vacuous when the sample
        # changed.
        from src.input.pdf_reader import read_pdf

        df, _ = read_pdf(PDF_PATH, password=PDF_PASSWORD)
        classifier = IBIClassifier()
        sells = [
            classifier.classify(r.to_dict())
            for _, r in df[(df["currency"] == "$") & (df["quantity"] < 0)].iterrows()
        ]
        sells = [s for s in sells if s["effect"] != "forex_sell"]
        assert sells, "sample PDF contains no USD sell rows"
        for result in sells:
            assert result["effect"] == "sell"
            assert result["market"] == "US"

    def test_us_tickers_are_not_truncated(self):
        # The name column truncates, so "(TICKER)" can lose its closing
        # paren; the leading-word fallback then yielded 'J.P'/'TEXAS' as the
        # symbol, which resolves to no real security.
        from src.input.pdf_reader import read_pdf

        df, _ = read_pdf(PDF_PATH, password=PDF_PASSWORD)
        us = df[df["currency"] == "$"]
        for _, r in us.iterrows():
            sym = str(r["security_symbol"])
            assert "." not in sym, f"{sym!r} looks like a truncated name, not a ticker"

    def test_forex_buy_still_special_cased_by_symbol(self):
        # symbol 99028 with tx_type translated to "קניה שח" must still hit
        # IBIClassifier's own symbol-99028 special case (forex_buy), not
        # the generic buy path -- confirms translation doesn't interfere
        # with symbol-based dispatch inside classify().
        from src.input.pdf_reader import read_pdf

        df, _ = read_pdf(PDF_PATH, password=PDF_PASSWORD)
        row = df[(df["security_symbol"] == "99028") & (df["amount_local_currency"] < 0)].iloc[0]
        result = IBIClassifier().classify(row.to_dict())
        assert result["effect"] == "forex_buy"
