"""Translate the PDF report's short transaction-type abbreviations to the
exact Hebrew strings IBIClassifier.classify() matches on (which come from
Excel's `סוג פעולה` column).

Why this exists: excel_reader.py passes through IBI's own full-length type
strings (e.g. "מכירה חול מטח") unchanged. The PDF report abbreviates the same
transaction types (e.g. "מ/חו\"ל") to save column width. IBIClassifier does
exact string matching on tx_type, so an unmapped PDF row silently falls
through every classify() branch to effect="none" and is dropped from the
portfolio build. This module closes that gap.

Two transforms, deliberately kept separate:

1. **Undo visual reversal.** pdfplumber returns RTL runs in visual order, so
   every Hebrew string arrives backwards ("דנדביד" is "דיבדנד" reversed).
   This is systematic and mechanical.
2. **Expand the abbreviation** to IBI's full Excel vocabulary
   ("מ/חו\"ל" -> "מכירה חול מטח"). This is a lookup, and it is not derivable
   from the reversal: only 1 of the 13 original entries round-tripped by
   reversal alone.

Keeping them separate means a newly-seen abbreviation needs one table entry
rather than a hand-transcribed reversed string, and the reversal is testable
on its own.

`translate_tx_type` raises `UnknownTransactionType` when it cannot produce a
string the classifier knows. The caller (pdf_reader) turns that into a
quarantine entry: a row the converter cannot express in the app's vocabulary
must not reach the database, where it would be inserted with effect="none"
and silently skipped by the builder.
"""
from typing import Optional


class UnknownTransactionType(Exception):
    """Raised when a PDF type abbreviation has no known translation.

    Carries the reversed (readable) form so the quarantine reason is
    legible rather than showing backwards Hebrew.
    """

    def __init__(self, pdf_type: str):
        self.pdf_type = pdf_type
        self.readable = reverse_rtl(pdf_type)
        super().__init__(
            f"no translation for PDF transaction type {pdf_type!r} "
            f"(reads as {self.readable!r})"
        )


# The vocabulary IBIClassifier.classify() matches, verbatim. A translation
# that is not in this set is a converter bug, not a classifier input.
CLASSIFIER_VOCABULARY = frozenset({
    "קניה שח", "קניה רצף", "קניה מעוף", "קניה חול מטח",
    "מכירה שח", "מכירה רצף", "מכירה מעוף", "מכירה חול מטח",
    "הפקדה", "הפקדה פקיעה", "הפקדה דיבידנד מטח",
    "משיכה", "משיכה פקיעה",
    "הטבה", "דיבדנד", "ריבית מזומן בשח", "משיכת ריבית מטח",
    "משיכת מס מטח", "משיכת מס חול מטח",
    "העברה מזומן בשח", "דמי טפול מזומן בשח",
})


def reverse_rtl(text: str) -> str:
    """Undo pdfplumber's visual ordering of an RTL run.

    pdfplumber emits RTL text in the order the glyphs are painted (right to
    left), so the logical string is the reverse. Applied to a pure-Hebrew
    token this is exact; mixed Hebrew/Latin tokens are handled by the caller
    (pdf_reader de-glues them before translation).
    """
    return text[::-1]


# Abbreviation (already un-reversed, i.e. readable) -> classifier vocabulary.
# Keys are what a human reads in the PDF, which makes them checkable against
# the report by eye.
_ABBREV_MAP = {
    # Transfers. Row: symbol 900, name "העברה רגילה" (regular transfer).
    "העברה": "העברה מזומן בשח",
    "העברה.": "העברה מזומן בשח",
    # Overseas market. מ = מכירה (sell), ק = קניה (buy). Rows: MSFT/AMZN/GOOG
    # with negative quantity and $ currency; SCHG positive.
    'מ/חו"ל': "מכירה חול מטח",
    'ק/חו"ל': "קניה חול מטח",
    # Continuous trading (רצף). Rows: Nesuah Vision sell, Nice buy, ₪.
    "מ/רציף": "מכירה רצף",
    "ק/רציף": "קניה רצף",
    # Options market (מעוף). Row: symbol 86761889, name "תP003540M610-35"
    # matching the option-naming regex, negative quantity = an option write.
    "מ/מעוף": "מכירה מעוף",
    "ק/מעוף": "קניה מעוף",
    # Deposit. Row name reverses to "הכנס/תשלום מעוף", one of
    # _PHANTOM_NAME_KEYWORDS verbatim. Checked against real Excel data for
    # this symbol/name pair (5039813): tx_type is "הפקדה" in 62/64 rows and
    # "משיכה" in 2, with no PDF-visible signal to tell them apart, so the
    # dominant case is used.
    "הפקדה": "הפקדה",
    # Deposit/dividend. Row: symbol 99028 (USD forex phantom), name
    # "הפ/דיב     JPM US".
    "הפ/דיב": "הפקדה דיבידנד מטח",
    # Tax withheld on the dividend just deposited; same 99028/JPM row pair,
    # negative quantity.
    "מש/מסח": "משיכת מס מטח",
    "מש/מס": "משיכת מס מטח",
    # Option expiry, deposit direction. Row: symbol 86507274, name
    # "תP003860M607-35" with positive quantity -> expiry credit.
    "ה/פקעה": "הפקדה פקיעה",
    # Dividend paid on a TASE holding. Row: Mizrahi Tefahot, ₪.
    "דיבדנד": "דיבדנד",
}

# Abbreviations whose meaning depends on the security, resolved by matching
# a keyword in the (un-reversed) security name. Ordered; first hit wins.
# Falls back to the `default` when no keyword matches.
_AMBIGUOUS_MAP = {
    # "מכירה" alone is either a forex sell (symbol 99028, name "דולר ארה\"ב")
    # or a tax row on proceeds (name "מס תקבולים"). These are different
    # transactions and must not collapse to one type.
    "מכירה": {
        "by_name": (
            ('דולר ארה"ב', "מכירה חול מטח"),
            ("מס", "משיכת מס מטח"),
        ),
        "default": "משיכת מס מטח",
    },
    # "קניה" covers the NIS->USD forex case (symbol 99028) and a phantom NIS
    # tax-payment row (name "מס ששולם"). IBIClassifier disambiguates by
    # symbol internally under its "קניה שח" branch, so both map there.
    "קניה": {
        "by_name": (),
        "default": "קניה שח",
    },
    # "משיכה" rows carry names "מס לשלם"/"מס עתידי" (tax to pay / future
    # tax) -> phantom tax withdrawal, matching _PHANTOM_NAME_KEYWORDS.
    "משיכה": {
        "by_name": (
            ("מס", "משיכת מס מטח"),
        ),
        "default": "משיכה",
    },
}


def translate_tx_type(
    pdf_type: str,
    security_symbol: str = "",
    security_name: Optional[str] = None,
) -> str:
    """Translate a PDF-report abbreviation to IBIClassifier's vocabulary.

    `pdf_type` and `security_name` are as extracted from the PDF, i.e. still
    in visual (reversed) order; both are un-reversed here.

    Raises UnknownTransactionType if no translation is known, so the caller
    can quarantine the row instead of handing the app a type it will
    silently drop.
    """
    raw = (pdf_type or "").strip()
    if not raw:
        raise UnknownTransactionType("")

    readable = reverse_rtl(raw)

    if readable in _ABBREV_MAP:
        return _ABBREV_MAP[readable]

    if readable in _AMBIGUOUS_MAP:
        rule = _AMBIGUOUS_MAP[readable]
        name = reverse_rtl((security_name or "").strip())
        for keyword, translated in rule["by_name"]:
            if keyword in name:
                return translated
        return rule["default"]

    # Already in the app's vocabulary (a PDF that spells the type out in
    # full, or a caller passing an Excel-sourced value through).
    if raw in CLASSIFIER_VOCABULARY:
        return raw
    if readable in CLASSIFIER_VOCABULARY:
        return readable

    raise UnknownTransactionType(raw)
