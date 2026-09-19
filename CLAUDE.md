# CLAUDE.md

## What This Is

Streamlit portfolio dashboard reconstructing investments from **IBI broker** (Israel) Excel exports. Tracks TASE/US positions separately, multi-currency (NIS/USD), historical prices, benchmark comparison.
More informations on the project: @docs\MASTER_PLAN.md

## Commands

```bash
streamlit run app.py
pytest
pytest tests/test_builder.py::test_buy_creates_position -v
pip install -r requirements.txt
```

## Architecture

```
IBI Excel (.xlsx) ─────────────────► excel_reader ─┐
IBI PDF report (.pdf, IMAP-fetched) → pdf_reader ──┴→ IBIClassifier → repository (SQLite) → builder → price_fetcher → dashboard
```

- **Ingestion** (`src/portfolio/ingestion.py`): Orchestrates pipeline — Excel or PDF → classify → FX rates → DB → builder. Dispatches on file extension.
- **PDF ingestion** (`src/input/pdf_reader.py`, `src/input/pdf_type_map.py`, `src/input/imap_fetcher.py`): Second input path — IBI's password-protected PDF account report, fetched unattended from Gmail over IMAP (app password; OAuth was abandoned because a Testing-status consent screen revokes refresh tokens every 7 days). See `docs/PDF_Ingestion_Plan.md` for the full design (char-coordinate row clustering, quarantine-not-guess for ambiguous rows, currency/type-abbreviation/ticker translation to match Excel's conventions).
- **Classifier** (`src/classifiers/ibi_classifier.py`): Maps 21 Hebrew IBI tx types to normalized effects. Extends `BaseClassifier` ABC.
- **Builder** (`src/portfolio/builder.py`): Sequential pass over transactions. Separate `positions_nis`/`positions_usd` dicts. Handles splits, option short-sells, phantom fills, expiry reordering. Writes `daily_portfolio_state` and `realized_trades`.
- **Price Fetcher** (`src/market/price_fetcher.py`): Twelvedata primary, yfinance fallback. Caches in `price_cache` table. Twelvedata needs a date *range* — `start_date == end_date` is rejected as an empty interval (HTTP 400) and `end_date` is exclusive, so the query spans `price_date - 10d` to `price_date + 1d` and picks the latest row ≤ `price_date`. Sending the same date for both silently disabled this source for a long time; every cached price came from yfinance.
- **Symbol Mapper** (`src/market/symbol_mapper.py`): Resolves IBI numeric IDs to tickers. Chain: runtime cache → DB → `_KNOWN_TASE_MAP` → TASE website API (`src/market/tase_api.py`, no key needed) → Twelvedata search.
- **Dashboard**: `app.py` → 7 tabs (Statistics, Performance, Cash Flow, TASE ₪, US $, Merged ₪, Options). Views in `src/dashboard/views/`, components in `src/dashboard/components/`.
- **Database**: SQLite `data/portfolio.db`. Tables: `transactions`, `fx_rates`, `price_cache`, `metadata`, `daily_portfolio_state`, `realized_trades`, `portfolio_snapshots`, `position_snapshots`, `tase_symbol_map`, `import_log`, `benchmark_cache`, `portfolio_current`. Schema in `src/database/db.py`.
- **Position** dataclass (`src/models/position.py`): quantity, total_invested, total_invested_nis, computed average_cost.

## Critical Domain Knowledge

- **PDF NIS cash**: the PDF report has no running cash-balance column (the one at x0~80 is post-trade *share count*), so PDF-sourced rows carry `balance=0.0`. The builder derives NIS cash solely from `balance`, so a PDF-only month cannot update NIS cash — it stays at whatever the last Excel import set. PDF ingestion therefore supplements, but does not replace, the quarterly Excel export.
- **PDF converter contract**: `pdf_reader` emits only `transaction_type` values in `pdf_type_map.CLASSIFIER_VOCABULARY` (the 21 literals `IBIClassifier.classify` matches). An untranslatable type raises `UnknownTransactionType` and the row is quarantined — never passed through, since the classifier has no `else` branch and would store it as `effect='none'`: in the DB but invisible to the builder.
- **RTL reversal**: pdfplumber returns Hebrew in visual order, so every Hebrew string from the PDF arrives reversed (`דנדביד` is `דיבדנד`). `pdf_type_map.reverse_rtl()` undoes this; abbreviation expansion (`מ/חו"ל` → `מכירה חול מטח`) is a separate step.
- **Agorot**: 100 agorot = 1 ₪. IBI stores TASE prices in agorot; `normalize_price()` divides by 100 at ingestion. yfinance `.TA` returns ILA (agorot) — `_normalize_tase()` always divides by 100. Twelvedata TASE prices use a per-price heuristic: > 10,000 → assumed agorot, divided by 100 (no TASE stock trades above ₪10,000).
- **Multi-currency**: NIS/USD positions in separate dicts. "Merged" view converts to NIS via FX rates.
- **Market detection**: Numeric IBI IDs (5-8 digits) → TASE, unless in `_KNOWN_US_NUMERIC_IDS`. `$` suffix → US. Options: 8-digit IDs starting with 8 or 9.
- **Phantoms**: Internal IBI entries (tax 999*, forex 99028, settlement 5039813) — `is_phantom=1`, filtered in builder, included for cash.
- **Option expiry reordering**: `_reorder_options_expiry()` ensures sells process before credits on same date.

## Configuration

- `.env`: `TWELVEDATA_API_KEY`, `YFINANCE_ENABLED=true`. Never log a request exception directly — `requests` embeds the resolved URL including `apikey=`; pass it through `src.config.redact()`.
- **Import automation**: `scripts/install_cron.sh` installs a *monthly* job (20th, 08:00 — reports arrive mid-month). `run_import.sh` snapshots the DB to `data/backups/` (last 10) before each run; `run_import.py` emails a summary on every outcome via `src/input/notifier.py` (Gmail SMTP, same app password as IMAP) and skips the ~8-minute rebuild when no rows were inserted.
- Excel input: `Trans_Input/Transactions_IBI.xlsx`
- PDF input (Gmail automation): `.env` — `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_APP_PASSWORD`, `IMAP_MAILBOX`, `IMAP_SEARCH_SENDER`, `IMAP_SEARCH_SUBJECT`, `IBI_PDF_PASSWORD`. The app password needs 2-Step Verification on the account (https://myaccount.google.com/apppasswords). Fetched PDFs land in `Trans_Input/pdf_archive/` (gitignored). Run manually: `venv/bin/python scripts/run_import.py`. Cron: `scripts/install_cron.sh` (not installed by default — see `docs/PDF_Ingestion_Plan.md`).
- Initial positions: `config/initial_positions.json`
- New TASE stock: resolved automatically via the TASE website API (`tase_api.py`); manual fallback is `_KNOWN_TASE_MAP` in `symbol_mapper.py`. US stock with numeric IBI ID: add to `_KNOWN_US_NUMERIC_IDS`.

## ReEvaluation
 - **Implimentation re-evaluation** the state of the app's implimentation is found in  @docs in a file called docs\Project_ReEvaluation_[Date of Evaluation].md