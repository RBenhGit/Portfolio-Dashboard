# PDF Ingestion — Design & Status (2026-09-05)

## What this is

A second transaction-import path alongside the Excel flow: IBI emails a
password-protected PDF "account report" (חוד לחשבון) periodically. This doc
covers fetching it automatically (Gmail) and parsing it into transactions.
Builds on `docs/Gmail_Fetch_Attempt_2026-08-19.md`, which covers the Gmail
fetch itself in detail (that piece is done — OAuth in Production mode,
`credentials.json` + cached `token.json`, verified unattended fetch).

## Why a PDF path at all, given Excel already works

Excel remains the primary, reliable source and is not being replaced. The
PDF path exists to close the automation gap between periodic Excel exports:
the sample PDF used to build this (`Trans_Input/IBI__000093395_001810.pdf`)
covers 2026-07-06 to 2026-08-05, strictly newer than the newest Excel file on
hand (`Trans_Input/Transactions_IBI_Q1_2026.xlsx`, ending 2026-03-31) — so a
weekly Gmail-fetched PDF genuinely covers the marginal gap Excel doesn't yet
have.

## Architecture

```
Gmail (IBI report, self-forwarded from ran@benhur.co)
      │  src/input/gmail_fetcher.py — OAuth, query search, PDF download
      ▼
Trans_Input/pdf_archive/*.pdf
      │  src/input/pdf_reader.py — char-coordinate row clustering + validation
      ▼
(DataFrame of clean rows, list of quarantined rows)
      │  src/input/pdf_type_map.py — abbreviation → Excel tx_type translation
      ▼
src/portfolio/ingestion.py — same classify/FX/dedup/build path as Excel
      │
      ▼
SQLite (transactions, daily_portfolio_state, realized_trades, ...)
```

`ingestion.ingest(source)` dispatches on file extension (`.pdf` vs
everything else) — see `src/portfolio/ingestion.py`. Both paths converge on
the same `IBIClassifier.classify()` / `repository.insert_transactions_deduped()`
call, so nothing downstream of ingestion needed to change.

Automation entry point: `scripts/run_import.py` (fetch → ingest, exit-code
contract 0/2/3/4) called by `scripts/run_import.sh` (cron wrapper, logs to
`logs/import_<date>.log`) installed via `scripts/install_cron.sh` (not yet
installed — see Outstanding below).

## Why the PDF needs a dedicated parser (not just `pdfplumber.extract_text()`)

Confirmed via direct `page.chars` (character-coordinate) inspection: the
report's rows aren't evenly spaced, and pdfplumber's `extract_text()` /
`extract_tables()` both garble the daily-transaction-log page because
adjacent rows (and even sub-fields within one row) can sit under 3pt apart —
closer than the normal ~7-11pt row pitch. `src/input/pdf_reader.py` instead
clusters `page.chars` into visual rows using a running-average `top`
tolerance (2.5pt), then validates each candidate row against the expected
transaction-row shape.

**On the real sample PDF, page 3 (the daily transaction log) yields 18 clean
rows and 14 quarantined rows** (roughly the ~80/20 split estimated during
initial investigation). Quarantined rows are never guessed at or inserted —
they're returned separately (`ingest()`'s `rows_quarantined` key) with the
raw character dump and a reason, for manual review against the source PDF.
This is a deliberate design choice: a wrong guess here would silently
corrupt position tracking, which is worse than a visible gap.

The holdings-summary table (pages 0-1, "תורתי טוריפ") is out of scope
entirely — it's a point-in-time snapshot, not transactions, and its data
genuinely bleeds into page 3's layout in places (see `pdf_reader.py`'s
module docstring for exactly how row-inclusion avoids that bleed-through
without relying on a fixed page region).

## Two translation gaps found and closed during implementation

These were caught by testing the parser's output *through* `IBIClassifier`
end-to-end, not just checking the parser's own output shape — both would
have silently dropped every PDF-sourced transaction if left unfixed:

1. **Currency codes**: the PDF prints `USD`/`ILS`; `IBIClassifier` and
   `symbol_mapper.detect_market()` check for the exact symbols `$`/`₪`
   (which is what Excel's own columns already contain). `pdf_reader.py`
   maps `USD→$`, `ILS→₪` before rows leave `read_pdf()`.
2. **Transaction-type abbreviations**: the PDF abbreviates tx types (e.g.
   `ל"וח/מ` for a USD sell) where Excel spells them out (`מכירה חול מטח`).
   `IBIClassifier.classify()` does exact string matching, so an unmapped
   abbreviation silently produces `effect="none"` and the row is dropped
   from the portfolio build with no error. `src/input/pdf_type_map.py`
   translates the ~13 observed abbreviations to Excel's vocabulary,
   derived by reversing each row's RTL text and cross-referencing against
   real Excel data for the same account/securities.
3. **US ticker vs. numeric ID**: the PDF always prints IBI's internal
   numeric security ID; Excel's own `security_symbol` column uses the plain
   ticker for US-market rows (e.g. `MICROSOFT(MSFT)` → `MSFT` in Excel, not
   IBI's numeric ID `105049`). `detect_market()` treats a purely-numeric
   symbol as TASE, so passing the numeric ID through for a genuine US stock
   would misclassify it. `pdf_reader.py` extracts the ticker from the
   security name for USD rows (matching Excel's own apparent convention),
   falling back to the numeric ID only when no ticker pattern is found.

All three are covered by `tests/test_pdf_type_map.py`'s
`TestEndToEndClassification`, which feeds real parsed PDF rows through the
actual `IBIClassifier` and asserts none unexpectedly classify as
`effect="none"`.

### Known pre-existing gap, not introduced by this work

Two specific phantom-row shapes (`tx_type="קניה שח"` with a `999*`-prefixed
tax symbol; `tx_type="הפקדה"` with symbol `5039813`/name `הכנס/תשלום מעוף`)
classify as `effect="none"` in `IBIClassifier` today **even when sourced
from Excel directly** — confirmed by feeding the same combinations from real
Excel data through `classify()` in isolation. Both branches require
`not is_phantom`, and these rows are phantom by symbol/name match. This is
an existing `IBIClassifier` limitation unrelated to the PDF path; fixing it
(if wanted) is a separate, narrowly-scoped task in `ibi_classifier.py`.

## Known gaps vs. Excel's output (by design, not guessed at)

- `additional_fees`, `capital_gains_tax_estimate`: no PDF equivalent found;
  always 0.0.
- `balance`: the PDF's daily log has no running-balance column comparable
  to Excel's `יתרה שקלית`; always 0.0.
- `amount_foreign_currency`: not printed as a clean column for USD rows in
  the PDF (only as a footnote a few points below the row); computed as
  `quantity × normalized_price` instead, validated against the PDF's own
  footnote lines during development.

See `src/input/pdf_reader.py`'s module docstring for the full column-to-x0
mapping and derivation, and `src/input/pdf_type_map.py` for the
abbreviation table with per-entry evidence.

## Outstanding / not yet done

1. **Cron not installed.** `scripts/install_cron.sh` exists and is
   idempotent (`./install_cron.sh` / `--remove`) but has not been run —
   installing a cron job is a real change to the user's system and was left
   as an explicit opt-in rather than done automatically. Installs a Monday
   08:00 weekly run.
2. **Manual-forward fragility**, carried over from
   `Gmail_Fetch_Attempt_2026-08-19.md`: the source email is a self-forward
   from `ran@benhur.co`, not a direct send from IBI. The cron is only as
   reliable as that manual forward happening every period. Fixing this is a
   mailbox configuration task (a Gmail auto-forward/filter rule at the
   source), not a code change — nothing in this repo can address it.
3. **Quarantine review is manual.** ~40% of quarantined rows on the sample
   PDF were genuinely ambiguous transactions (e.g. the PLTR trade) lost to
   character-level overlap in IBI's own report layout — not a parser
   shortcoming fixable with more clustering cleverness (verified at the
   `page.chars` level: two rows' glyphs interleave within under 2pt).
   These need to be entered manually (cross-checked against a later Excel
   export once available, or read directly from the PDF by eye) until/unless
   IBI's report generator changes.
4. **Only the daily transaction log (page 3) is parsed.** The holdings
   summary table is out of scope by design (point-in-time snapshot, not
   transactions) — no work needed there unless a future use case requires
   point-in-time holdings reconciliation.
