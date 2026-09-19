"""Read IBI's password-protected PDF "account report" (חוד לחשבון) -> DataFrame.

This is a second input path alongside `excel_reader.py`. IBI's monthly Excel
export is a clean flat table; the PDF report is not: pdfplumber's
`extract_text()` and `extract_tables()` both garble the daily-transaction-log
rows because the report's row spacing is uneven and (per row) sometimes
overlaps character-level with an unrelated table bleeding through the same
page. So this module works at the `page.chars` level directly, clusters
characters into visual rows by `top` with a small tolerance, and only accepts
a clustered row as a transaction if it passes strict validation. Anything
that doesn't validate is quarantined rather than guessed at — see `read_pdf()`.

## Page layout (as observed in Trans_Input/IBI__000093395_001810.pdf, a real
## 4-page IBI monthly report)

- Page 0 (`pdf.pages[0]`): cover + a "תורתי טוריפ" (holdings detail) summary
  table. OUT OF SCOPE — this is a point-in-time snapshot, not transactions.
- Page 1 (`pdf.pages[1]`): legal/disclosure text plus the same holdings
  table continuing. OUT OF SCOPE.
- Page 2 (`pdf.pages[2]`, i.e. "page 3" in the PDF's own 1-indexed footer):
  the daily transaction log. IN SCOPE — this is the primary target of this
  module.
- Page 3 (`pdf.pages[3]`): near-empty trailer page. OUT OF SCOPE.

### The page-2 holdings-table bleed-through (important correction vs. the
### original hypothesis that this was confined to top>=600)

The holdings-detail table from pages 0-1 is NOT confined to a clean block at
the bottom of page 2. It actually starts interleaving with the transaction
log as early as top ~247 (its rows are recognizable by a leading
percentage-like number `NN.NN` under 100, e.g. "13.09", "5.81" -- IBI's
"percent of portfolio" column) and continues, increasingly garbled with
itself, through the bottom of the page (~top 750). Below approximately
top ~601 it stops interleaving with transaction rows entirely and becomes a
self-contained (if badly overlapping) continuation of the holdings table
using a *different* column x-grid than the transaction log above it.

This module does not rely on a fixed top cutoff to exclude this table.
Instead, a transaction row must start with a clean `DD/MM/YY` date at
x0~24.8 (see `_DATE_X0`, `_DATE_RE`); holdings-table fragments never satisfy
that, whether they appear standalone (harmlessly ignored) or glued into a
transaction row's date field (which breaks the date match, so the whole
row correctly falls through to quarantine instead of being silently
mis-parsed). `HOLDINGS_TABLE_TOP_RANGE` below documents the observed
approximate extent of the bleed-through for reference, but is NOT used as a
row-inclusion filter.

## Column mapping (x0 = left edge of the character/word, in PDF points)

Reverse-engineered by cross-referencing parsed values against
`Trans_Input/Transactions_IBI_Q1_2026.xlsx` (same account, prior quarter,
read via pandas) for: (a) commission values matching Excel's commission
vocabulary (7.5, 7.51, 2.35, ...), and (b) `execution_price * quantity`
reproducing IBI's own in-PDF verification footnote line for USD trades
(e.g. "776.00 USD ....חטמב יוכיז" directly below a MSFT row) and reproducing
`quantity * price/100 ~= amount_local_currency` (net of commission) for ILS
trades. See docs in the module for the row-clustering approach; the mapping
below is what that cross-check converged on:

    x0 ~24.8          -> date (trade date, DD/MM/YY)
    x0 ~80-99          -> post-execution running quantity (position balance
                           after this trade). NOT part of the target schema;
                           not extracted.
    x0 ~143-161        -> currency word ("USD" / "ILS"), absent for NIS-only
                           phantom/transfer rows.
    x0 ~184-201        -> commission
    x0 ~205-242        -> amount, local currency (NIS). 0.00 for pure-USD
                           trades (matches Excel's `תמורה בשקלים` column,
                           which is likewise 0 for USD trades there).
    x0 ~250-290        -> execution price, RAW. For USD rows this is the
                           real price scaled x100 in the PDF's own display
                           formatting and must be divided by 100 to match
                           Excel's `שער ביצוע` (plain-dollar) convention.
                           For ILS rows it is already raw agorot, matching
                           Excel's TASE convention exactly (no division) --
                           see `_normalize_pdf_price()`.
    x0 ~295-321        -> execution quantity, signed as printed.
    x0 ~340-370        -> transaction type (Hebrew abbreviation). Translated
                           to IBIClassifier's exact Excel-vocabulary string
                           via `pdf_type_map.translate_tx_type()` before
                           this module returns it -- the PDF's abbreviations
                           never match IBIClassifier's literal string
                           comparisons on their own, which would otherwise
                           silently classify every PDF row as effect="none"
                           and drop it from the portfolio build. See
                           `src/input/pdf_type_map.py` for the mapping and
                           the row-level evidence behind each entry.
    x0 ~370-437        -> security name (sometimes glued to the type text
                           with no separating space -- handled by prefix
                           stripping of the recognized short type codes).
    x0 ~440-470        -> security id (IBI's internal numeric security
                           identifier). For USD rows (other than the 99028
                           forex wrapper), this module substitutes a ticker
                           extracted from the security name instead -- see
                           `_extract_us_ticker()` -- because Excel's own
                           `security_symbol` column uses the ticker for US
                           rows, not this numeric id, and detect_market()
                           treats a purely-numeric symbol as TASE unless it
                           is in `_KNOWN_US_NUMERIC_IDS`. ILS rows keep the
                           raw numeric id unchanged (matches Excel there).
    x0 ~480-500        -> execution time (optional). Not part of the target
                           schema; not extracted.
    x0 ~500-527        -> value date (second date). Not part of the target
                           schema; not extracted.

## Known gaps vs. excel_reader.py's output (documented, not guessed at)

- `additional_fees`: the PDF has no equivalent to Excel's `עמלות נלוות`
  column. Always defaults to 0.0.
- `capital_gains_tax_estimate`: no PDF equivalent to `אומדן מס רווחי הון`.
  Always defaults to 0.0.
- `amount_foreign_currency`: the PDF never prints this as a clean column
  value for USD trades -- it only ever appears as a verification footnote
  a few points below the row (e.g. "776.00 USD"), which is itself one of
  the "aux" (non-primary) clustered rows and is not reliably attributable
  back to its parent row when rows are dense. Instead this module computes
  it as `quantity * normalized_price` (validated against the footnote
  during development -- see module docstring above), signed by quantity.
  For ILS rows amount_foreign_currency is always 0.0 (mirrors Excel, where
  `תמורה במט"ח` is 0 for NIS-denominated trades).
- `security_symbol`: often just IBI's internal numeric security id (not a
  ticker), because a clean ticker isn't always separable from the security
  name text. Downstream `symbol_mapper.py` already knows how to resolve
  numeric IBI ids, so this matches Excel's own convention for e.g. option
  rows and non-US-ticker rows.
- Currency normalization: this module maps the PDF's 3-letter currency
  codes (`USD`, `ILS`) to the single-character symbols `excel_reader.py`
  emits directly from IBI's Excel headers (`$`, `₪`) so that
  `normalize_price()` (which checks `currency.strip() == "₪"` exactly) and
  `detect_market()` (which checks `cur == "$"` exactly) classify PDF-sourced
  rows identically to Excel-sourced ones. A blank/absent currency field
  (phantom, transfer, and interest rows never print a currency word) is
  mapped to `₪`, matching how IBI represents these same transaction types
  in the Excel export (e.g. `העברה מזומן בשח`, `5039813` phantom rows are
  always `₪` there).
"""
import hashlib
import re
from pathlib import Path
from typing import List, Optional, Tuple, Union

import pandas as pd
import pdfplumber

from src.market.symbol_mapper import resolve_us_numeric_ticker
from src.input.pdf_type_map import (
    CLASSIFIER_VOCABULARY,
    UnknownTransactionType,
    translate_tx_type,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Pages in scope / out of scope (0-indexed, matching pdfplumber's pdf.pages).
IN_SCOPE_PAGES = (2,)  # the daily transaction log ("page 3" in the PDF's own footer)
OUT_OF_SCOPE_PAGES = {
    0: "cover + holdings-detail summary table (point-in-time snapshot, not transactions)",
    1: "legal/disclosure text + holdings-detail table continuation",
    3: "near-empty trailer page",
}
# Approximate `top` extent of the holdings-table bleed-through on the in-scope
# page, for documentation only -- NOT used to filter rows (see module
# docstring: row inclusion is decided per-row by strict date validation).
HOLDINGS_TABLE_TOP_RANGE = (247, 750)

# Output columns, matching excel_reader.py's read_excel() contract.
OUTPUT_COLUMNS = [
    "date", "transaction_type", "security_name", "security_symbol",
    "quantity", "execution_price_raw", "currency", "commission",
    "additional_fees", "amount_foreign_currency", "amount_local_currency",
    "balance", "capital_gains_tax_estimate", "row_hash",
]

_NUMERIC_COLS = [
    "quantity", "execution_price_raw", "commission", "additional_fees",
    "amount_foreign_currency", "amount_local_currency",
    "balance", "capital_gains_tax_estimate",
]

# Row clustering tolerance (points). Chars within this `top` distance of the
# running cluster average are considered the same visual row. Neither
# round(top) grouping (over-merges rows ~1-2pt apart that are genuinely
# distinct) nor exact-match grouping (under-merges a single row whose chars
# have sub-point top jitter) works; this must be a running-average tolerance.
ROW_TOP_TOLERANCE = 2.5

# A clean transaction row's date starts here (points from left edge).
_DATE_X0 = 24.8
_DATE_X0_TOLERANCE = 1.0
_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")

# Column x0 bands (see module docstring for how these were derived).
_COL_CURRENCY = (140.0, 165.0)
_COL_COMMISSION = (183.0, 203.0)
_COL_AMOUNT_LOCAL = (204.0, 244.0)
_COL_PRICE = (249.0, 291.0)
# Right-aligned at x1~321.2, so x0 moves left as the value widens: a 9-char
# quantity like '-5,000.00' starts at 293.69 and was missed by a 294.0 edge,
# quarantining real forex sells and tax withdrawals. The price column ends at
# 291.0, so 292.0 recovers them without overlapping it.
_COL_QUANTITY = (292.0, 322.0)
_COL_TYPE = (338.0, 371.0)
_COL_SECURITY_NAME = (369.0, 438.0)
_COL_SECURITY_ID = (439.0, 471.0)

_CURRENCY_MAP = {"USD": "$", "ILS": "₪"}
_DEFAULT_CURRENCY = "₪"  # phantom/transfer/interest rows print no currency word

# Excel's own `security_symbol` column for US-market rows is the plain
# ticker (e.g. "MSFT"), NOT IBI's internal numeric id, extracted by IBI
# itself from the security name -- confirmed against Trans_Input's real
# Excel data: "MICROSOFT(MSFT)" -> symbol "MSFT", "AMZN <heb name>" ->
# symbol "AMZN", "GOOG US" -> symbol "GOOG". detect_market() in
# symbol_mapper.py treats a purely-numeric symbol as TASE unless it's in
# _KNOWN_US_NUMERIC_IDS, so passing IBI's numeric id through unchanged for
# these rows would misclassify a genuine US stock as TASE. The PDF report
# always prints the numeric id (never the ticker) in its security-id
# column, so this module must derive the ticker from the name text itself,
# the same way IBI's own Excel export apparently does.
_TICKER_PAREN_RE = re.compile(r"\(([A-Z][A-Z0-9.]{0,6})(?:\s+US)?\)")  # "NAME(TICKER)" / "NAME (TICKER US)"
_TICKER_US_RE = re.compile(r"^([A-Z][A-Z0-9.]{0,6})\s+US$")   # "TICKER US"
_TICKER_LEADING_RE = re.compile(r"^([A-Z][A-Z0-9.]{2,6})\b")  # "TICKER <heb name>" / bare "TICKER"
# The name column truncates at its width, so a trailing "(TICKER)" can lose
# its closing paren ("J.P. MORGAN(JPM", "TEXAS PACIF(TPL"). Without this the
# leading-word rule fires instead and yields 'J.P'/'TEXAS' as the symbol.
_TICKER_PAREN_TRUNC_RE = re.compile(r"\(([A-Z][A-Z0-9.]{0,6})$")


def _extract_us_ticker(name_text: str) -> Optional[str]:
    """Best-effort extraction of a US ticker from a security name, matching
    the pattern Excel's own `security_symbol` column follows for US rows.
    Returns None if no confident ticker-shaped token is found (caller then
    falls back to the raw numeric security id, same as Excel does for the
    small set of ids in _KNOWN_US_NUMERIC_IDS that never got a ticker)."""
    m = _TICKER_PAREN_RE.search(name_text)
    if m:
        return m.group(1)
    m = _TICKER_PAREN_TRUNC_RE.search(name_text.rstrip())
    if m:
        return m.group(1)
    m = _TICKER_US_RE.match(name_text)
    if m:
        return m.group(1)
    m = _TICKER_LEADING_RE.match(name_text)
    if m:
        return m.group(1)
    return None


class _Word:
    __slots__ = ("x0", "x1", "top", "text")

    def __init__(self, x0: float, x1: float, top: float, text: str):
        self.x0 = x0
        self.x1 = x1
        self.top = top
        self.text = text


def _cluster_rows(chars: list, tol: float = ROW_TOP_TOLERANCE) -> List[list]:
    """Group chars into visual rows, then split each group into sublines.

    Two stages, because neither alone is correct:

    1. Cluster by `top` with a running-average tolerance. This absorbs the
       sub-point baseline jitter within one visual line (gaps of 0.1-1.4pt
       are the same line rendered with slight font variation).

    2. Split each cluster by *exact* `top`. IBI's row pitch can put two
       genuinely different lines under `tol` apart, and stage 1 merges them
       -- 51% of clusters on the sample PDFs held more than one line. Since
       `_row_to_words` then sorts purely by x0, a merged cluster interleaves
       the two lines' characters and produces garbage like '13/08/21600.00'
       (a date fused with the amount from the line below). Splitting here
       keeps each emitted row on a single baseline, so x0 ordering is the
       real reading order.

    Stage 2 is safe precisely because stage 1 already ran: chars of one
    visual line share an exact `top` in this PDF (verified on both sample
    reports), so the split separates lines without fragmenting them.
    """
    chars_sorted = sorted(chars, key=lambda c: c["top"])
    clusters: List[list] = []
    cur: list = []
    cur_top = None
    for c in chars_sorted:
        if cur and abs(c["top"] - cur_top) > tol:
            clusters.append(cur)
            cur = []
        cur.append(c)
        cur_top = sum(x["top"] for x in cur) / len(cur)
    if cur:
        clusters.append(cur)

    rows: List[list] = []
    for cluster in clusters:
        by_top: dict = {}
        for c in cluster:
            by_top.setdefault(round(c["top"], 1), []).append(c)
        for _, subline in sorted(by_top.items()):
            rows.append(subline)
    return rows


def _row_to_words(row_chars: list, x_gap: float = 1.5) -> List[_Word]:
    """Group a row's chars into words by x-proximity, left-to-right by x0."""
    row_chars = sorted(row_chars, key=lambda c: c["x0"])
    words: List[list] = []
    cur: list = []
    for c in row_chars:
        if cur and (c["x0"] - cur[-1]["x1"]) > x_gap:
            words.append(cur)
            cur = []
        cur.append(c)
    if cur:
        words.append(cur)
    out = []
    for w in words:
        text = "".join(c["text"] for c in w)
        if not text.strip():
            continue  # drop pure-whitespace tokens (real chars in the PDF's own stream)
        out.append(_Word(w[0]["x0"], w[-1]["x1"], sum(c["top"] for c in w) / len(w), text))
    return out


def _words_in_band(words: List[_Word], band: Tuple[float, float]) -> List[_Word]:
    lo, hi = band
    return [w for w in words if lo <= w.x0 <= hi]


def _split_glued_type_name(raw: str, fallback_type: str) -> Tuple[str, str]:
    """Split a word where the type and security name ran together.

    The PDF prints them with no separating space (e.g. 'ל"וח/מMICROSOFT(MSFT)'),
    so they arrive as one token. Split at the transition from the Hebrew type
    to the Latin/digit run that starts the name. Returns (type, name); the
    name is empty when no such transition exists (a wholly Hebrew name, which
    cannot be split this way).
    """
    m = re.search(r"[A-Za-z0-9(]", raw)
    if m and m.start() > 0:
        return raw[: m.start()].strip() or fallback_type, raw[m.start():].strip()
    return fallback_type, raw if raw != fallback_type else ""


def _has_transaction_shape(words: List[_Word]) -> bool:
    """True if the row carries the columns only a transaction has.

    Distinguishes a corrupted transaction row (worth quarantining) from
    holdings-table bleed-through (correctly skipped). Every transaction row
    carries a real type and a security id; a holdings row carries neither,
    however far left its leading number happens to start.

    The type must contain an actual word character: a holdings row's column
    separator '/' lands in the type band and would otherwise pass, and its
    right-hand numbers can reach the id band, so a bare non-empty check on
    both bands is not enough.
    """
    type_words = _words_in_band(words, _COL_TYPE)
    has_real_type = any(re.search(r"[^\W_]", w.text) for w in type_words)
    return has_real_type and bool(_words_in_band(words, _COL_SECURITY_ID))


def _parse_number(text: str) -> Optional[float]:
    """Parse a PDF-extracted numeric token (handles thousands separators)."""
    t = text.strip().replace(",", "")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _normalize_pdf_price(raw_price: float, currency_code: str) -> float:
    """Undo the PDF's own x100 display scaling for USD, matching Excel's
    `execution_price_raw` convention exactly (see module docstring).

    - ILS rows: already raw agorot in the PDF, same as Excel -- no change.
    - USD rows: PDF prints price x100 relative to Excel's plain-dollar
      convention -- divide by 100.
    """
    if currency_code == "USD":
        return raw_price / 100.0
    return raw_price


def _hash(row: pd.Series) -> str:
    """SHA256 of joined string values -- mirrors excel_reader.py exactly."""
    return hashlib.sha256("|".join(str(v) for v in row.values).encode()).hexdigest()


def _parse_primary_row(row_chars: list, page_number: int) -> Tuple[Optional[dict], Optional[dict]]:
    """Attempt to parse one clustered row into a transaction dict.

    Returns (parsed_dict, None) on success, or (None, quarantine_dict) on
    failure. Never guesses: any ambiguity or missing required field routes
    to quarantine instead of a best-effort value.
    """
    tops = [c["top"] for c in row_chars]
    top_min, top_max = min(tops), max(tops)
    words = _row_to_words(row_chars)
    if not words:
        return None, None

    first = words[0]
    if not (abs(first.x0 - _DATE_X0) <= _DATE_X0_TOLERANCE and _DATE_RE.match(first.text)):
        # Not a primary transaction row (footnote, disclaimer, holdings-table
        # fragment, or a row whose date got corrupted by character overlap
        # with the holdings-table bleed-through). Not an error by itself --
        # caller decides whether to quarantine based on other signals.
        return None, None

    date_text = first.text

    def _band_text(band):
        matches = _words_in_band(words, band)
        return matches

    reasons = []

    currency_words = _band_text(_COL_CURRENCY)
    currency_code = currency_words[0].text.strip() if currency_words else ""
    if currency_code and currency_code not in _CURRENCY_MAP:
        reasons.append(f"unrecognized currency code {currency_code!r}")

    commission_words = _band_text(_COL_COMMISSION)
    commission = _parse_number(commission_words[0].text) if commission_words else 0.0
    if commission_words and commission is None:
        reasons.append(f"unparseable commission {commission_words[0].text!r}")

    amount_local_words = _band_text(_COL_AMOUNT_LOCAL)
    amount_local = _parse_number(amount_local_words[0].text) if amount_local_words else 0.0
    if amount_local_words and amount_local is None:
        reasons.append(f"unparseable amount_local {amount_local_words[0].text!r}")

    price_words = _band_text(_COL_PRICE)
    price_raw = _parse_number(price_words[0].text) if price_words else None
    if not price_words:
        reasons.append("missing price field")
    elif price_raw is None:
        reasons.append(f"unparseable price {price_words[0].text!r}")

    qty_words = _band_text(_COL_QUANTITY)
    quantity = _parse_number(qty_words[0].text) if qty_words else None
    if not qty_words:
        reasons.append("missing quantity field")
    elif quantity is None:
        reasons.append(f"unparseable quantity {qty_words[0].text!r}")

    security_id_words = _band_text(_COL_SECURITY_ID)
    security_id = security_id_words[0].text.strip() if security_id_words else ""
    if security_id_words and not re.fullmatch(r"\d{2,9}", security_id):
        reasons.append(f"implausible security id {security_id!r}")

    type_words = _band_text(_COL_TYPE)
    name_words = _band_text(_COL_SECURITY_NAME)
    # Type and name sometimes glue together with no space (e.g.
    # 'ל"וח/מMICROSOFT(MSFT)'); when that happens both bands pick up the
    # same merged word. Prefer the type-band word as the type, and if the
    # name-band word is identical to it (i.e. genuinely glued), split by
    # locating the transition from Hebrew/punctuation to a Latin/digit run.
    type_text = type_words[0].text.strip() if type_words else ""
    if name_words:
        raw_name = name_words[0].text.strip()
        if type_words and raw_name == type_text:
            type_text, name_text = _split_glued_type_name(raw_name, type_text)
        else:
            name_text = raw_name
    else:
        # The glued word can land in the type band alone (its x0 falls left
        # of the name band), leaving no name word at all -- this is how the
        # TSLA/NOW sells lost their security_name, which in turn stopped the
        # US-ticker lookup and mislabelled them as market='TASE'.
        type_text, name_text = _split_glued_type_name(type_text, type_text)

    if not name_text and not security_id:
        reasons.append("no security name or id found")

    # Translate before the reasons check: a type the app has no vocabulary for
    # is a conversion failure, and the row must be quarantined rather than
    # handed to the classifier, which has no `else` branch and would insert it
    # with effect="none" -- present in the DB but invisible to the builder.
    transaction_type = None
    try:
        transaction_type = translate_tx_type(type_text, security_id, name_text)
    except UnknownTransactionType as exc:
        reasons.append(str(exc))

    if reasons:
        return None, {
            "page": page_number,
            "top_range": (round(top_min, 1), round(top_max, 1)),
            "raw_chars": "".join(c["text"] for c in sorted(row_chars, key=lambda c: c["x0"])),
            "reason": "; ".join(reasons),
        }

    currency_out = _CURRENCY_MAP.get(currency_code, _DEFAULT_CURRENCY)
    price_norm = _normalize_pdf_price(price_raw, currency_code or "ILS")
    amount_fx = round((quantity or 0.0) * price_norm, 2) if currency_code == "USD" else 0.0

    # US-market rows: prefer a ticker extracted from the name over IBI's raw
    # numeric id, matching Excel's own convention (see _extract_us_ticker's
    # docstring). symbol 99028 (the NIS<->USD forex wrapper) is excluded --
    # IBIClassifier's own symbol-99028 special case depends on that exact
    # value and must not be overridden by a ticker guess.
    security_symbol_out = security_id
    if currency_code == "USD" and security_id != "99028":
        ticker = _extract_us_ticker(name_text)
        if not ticker:
            # Some USD rows print no security name at all, so there is
            # nothing to extract from. Fall back to the app's existing map of
            # US securities that carry a numeric IBI id -- without this the
            # bare numeric id reaches detect_market(), which reads it as TASE
            # and mislabels a US trade.
            ticker = resolve_us_numeric_ticker(security_id)
        if ticker:
            security_symbol_out = ticker

    return {
        "date": date_text,
        "transaction_type": transaction_type,
        "security_name": name_text,
        "security_symbol": security_symbol_out,
        "quantity": quantity,
        "execution_price_raw": price_norm,
        "currency": currency_out,
        "commission": commission,
        "additional_fees": 0.0,
        "amount_foreign_currency": amount_fx,
        "amount_local_currency": amount_local,
        "balance": 0.0,
        "capital_gains_tax_estimate": 0.0,
    }, None


def read_pdf(path: Union[str, Path], password: Optional[str] = None) -> Tuple[pd.DataFrame, List[dict]]:
    """Read IBI's PDF account report -> (DataFrame, quarantined_rows).

    Mirrors `excel_reader.read_excel()`'s output columns and conventions
    (sorted ascending by date, `row_hash` = sha256 of joined string values)
    but returns a tuple instead of a single DataFrame: unlike an Excel row,
    a PDF row can be genuinely unparseable (character-level overlap between
    two logical rows, corrupted by the holdings-table bleed-through -- see
    module docstring) and must not be silently dropped or guessed at.
    Anything that fails validation is returned in `quarantined_rows` instead.

    Only `IN_SCOPE_PAGES` (currently just the daily transaction log) is
    parsed; see module docstring for what's out of scope and why.
    """
    rows: List[dict] = []
    quarantined: List[dict] = []

    with pdfplumber.open(str(path), password=password) as pdf:
        for page_idx in IN_SCOPE_PAGES:
            if page_idx >= len(pdf.pages):
                continue
            page = pdf.pages[page_idx]
            clustered = _cluster_rows(page.chars)
            for row_chars in clustered:
                words = _row_to_words(row_chars)
                if not words:
                    continue
                first = words[0]
                looks_like_date_start = _DATE_RE.match(first.text) and abs(first.x0 - _DATE_X0) <= _DATE_X0_TOLERANCE
                # A row whose first word starts near the date column but is
                # NOT a clean date (e.g. '14/07/21600.00') is a corrupted
                # primary row -- quarantine it explicitly rather than
                # silently skipping (it's not a footnote/disclaimer, it's a
                # broken transaction).
                near_date_col = abs(first.x0 - _DATE_X0) <= 3.0
                if not looks_like_date_start and not near_date_col:
                    continue  # footnote / disclaimer / holdings-table fragment -- not a transaction row
                if not looks_like_date_start and not _has_transaction_shape(words):
                    # Holdings-table bleed-through: its leading number can land
                    # in the date column, but it carries neither a transaction
                    # type nor a security id. Not a broken transaction, so
                    # skipping is correct -- quarantining it would report a
                    # data loss that did not occur.
                    continue
                parsed, quarantine = _parse_primary_row(row_chars, page_idx)
                if parsed is not None:
                    rows.append(parsed)
                elif quarantine is not None:
                    quarantined.append(quarantine)
                elif near_date_col and not looks_like_date_start:
                    tops = [c["top"] for c in row_chars]
                    quarantined.append({
                        "page": page_idx,
                        "top_range": (round(min(tops), 1), round(max(tops), 1)),
                        "raw_chars": "".join(c["text"] for c in sorted(row_chars, key=lambda c: c["x0"])),
                        "reason": f"date field did not match DD/MM/YY pattern: {first.text!r}",
                    })

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), quarantined

    df = pd.DataFrame(rows)

    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%y", errors="coerce")
    bad_dates = df["date"].isna()
    if bad_dates.any():
        for _, r in df[bad_dates].iterrows():
            quarantined.append({
                "page": IN_SCOPE_PAGES[0],
                "top_range": None,
                "raw_chars": str(r.to_dict()),
                "reason": "date failed to parse after extraction",
            })
        df = df[~bad_dates].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df = df.sort_values("date", ascending=True).reset_index(drop=True)

    df["currency"] = df["currency"].str.strip()
    df["security_symbol"] = df["security_symbol"].astype(str).str.strip()

    df["row_hash"] = df.apply(_hash, axis=1)

    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df = df[OUTPUT_COLUMNS]

    return df, quarantined
