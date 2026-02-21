# Project Re-Evaluation Report
**Date:** 2026-02-20
**Focus:** Full Project — Post-refactor assessment (historical prices, split tabs, TASE labels)

## Executive Summary

The Portfolio Dashboard is a well-structured Streamlit application with clean module separation and consistent function signatures. However, a recent series of refactors (historical price fetching, 3-tab split, TASE ticker labels) have introduced **documentation drift** in `MASTER_PLAN.md`, left **8 dead constants** in `config.py`, and the project has **0% test coverage** across 31 Python files. No broken imports or signature mismatches were found — the code is internally consistent.

---

## Findings

### 1. Documentation Accuracy (MASTER_PLAN.md vs Code)

| Area | MASTER_PLAN.md Says | Code Does | Status |
|------|---------------------|-----------|--------|
| Tab layout | "2 tabs: Portfolio (NIS+USD side-by-side), Merged (₪)" | 3 tabs: TASE (₪), US ($), Merged (₪) — each full-width | **Mismatch** |
| Price fetching | "GET /price (live), cache TTL = 10min US / 60min TASE" | Historical /time_series for a specific date, no TTL (permanent cache) | **Mismatch** |
| price_cache schema | "PRIMARY KEY (symbol, market)" | PRIMARY KEY (symbol, market, price_date) — added price_date column | **Mismatch** |
| Merged view FX | "current_fx_rate (live)" | `repository.get_fx_rate(price_date)` — historical FX for reference date | **Mismatch** |
| Chart labels | Uses raw symbol (e.g., "445015") | `_display_label()` resolves TASE tickers (e.g., "MTRX") | **Mismatch** |
| TASE symbol 507012 | "EMCO" / "E&M Computing" | "CMDR" / "Computer Direct" | **Mismatch** |
| portfolio_view.render() | Takes `(portfolio, prices)` | Takes `(positions, prices, currency_symbol, cash, title)` | **Mismatch** |
| merged_view.render() | Takes `(portfolio, prices)` | Takes `(portfolio, prices, price_date)` | **Mismatch** |
| PRICE_TTL constants | Documented as active (600s / 3600s) | Defined in config.py but never imported or used | **Mismatch** |
| Transaction classification (21 types) | Fully documented | Matches implementation | Match |
| Portfolio builder logic | Documented cost basis rules | Matches implementation | Match |
| Phantom detection rules | Documented in MASTER_PLAN | Matches ibi_classifier.py implementation | Match |
| FX historical bulk fetch | "/time_series?symbol=USD/ILS" | Matches fx_fetcher.py | Match |
| Deduplication via row_hash | Documented | Matches repository.py | Match |

### 2. Dead Code / Unused Constants in config.py

| Constant | Line | Defined Value | Actually Used? | Notes |
|----------|------|---------------|----------------|-------|
| `PRICE_TTL_US_SEC` | 20 | `600` | No | Replaced by date-based cache (no TTL) |
| `PRICE_TTL_TASE_SEC` | 21 | `3600` | No | Replaced by date-based cache (no TTL) |
| `OPTION_SYMBOL_PATTERN` | 24 | `r'^[89]\d{7}$'` | No | Duplicated in ibi_classifier.py and symbol_mapper.py as private `_OPTION_RE` |
| `US_TICKER_SYMBOL_PATTERN` | 25 | `r'^[A-Z]{1,6}$'` | No | Duplicated in ibi_classifier.py and symbol_mapper.py as private `_US_TICKER_RE` |
| `TASE_NUMERIC_PATTERN` | 26 | `r'^\d{5,8}$'` | No | Duplicated in ibi_classifier.py and symbol_mapper.py as private `_TASE_NUM_RE` |
| `PHANTOM_SYMBOL_PREFIXES` | 29 | `("999",)` | No | Never referenced anywhere |
| `PHANTOM_SYMBOLS` | 30 | `{"99028", "5039813"}` | No | Duplicated in ibi_classifier.py as `_PHANTOM_SYMBOLS` |
| `PHANTOM_NAME_KEYWORDS` | 31-34 | Hebrew keywords | No | Duplicated in ibi_classifier.py as `_PHANTOM_NAME_KEYWORDS` |

**8 of 14 constants (57%) are dead code.** Only `BASE_DIR`, `EXCEL_PATH`, `DB_PATH`, `TWELVEDATA_API_KEY`, `YFINANCE_ENABLED`, and `TASE_PRICE_IN_AGOROT` are actually used.

### 3. Configuration Alignment

| Variable | .env.example | config.py | Code Usage | Status |
|----------|-------------|-----------|------------|--------|
| `TWELVEDATA_API_KEY` | `your_key_here` | Line 16, `os.getenv(...)` | price_fetcher, symbol_mapper, fx_fetcher | Aligned |
| `YFINANCE_ENABLED` | `true` | Line 17, `os.getenv(...)` | price_fetcher.py:60 | Aligned |
| `PRICE_TTL_US_SEC` | N/A (not in .env) | Line 20 hardcoded | **Not used anywhere** | Dead |
| `PRICE_TTL_TASE_SEC` | N/A (not in .env) | Line 21 hardcoded | **Not used anywhere** | Dead |

### 4. Import & Signature Consistency

All 50+ imports across 21 source files resolve correctly. All function call sites pass the correct arguments matching current signatures. No broken imports, no signature mismatches.

Key verifications:
- `repository.get_cached_price(symbol, market, price_date)` — all callers pass 3 args correctly
- `repository.upsert_price(..., price_date)` — caller in price_fetcher.py passes 6 args correctly
- `fetch_prices_for_positions(positions, price_date)` — app.py passes both args
- `merged_view.render(portfolio, prices, price_date)` — app.py passes 3 args
- `portfolio_view.render(positions, prices, currency, cash, title)` — app.py passes 5 args (2 calls)
- `charts._display_label(sym, pos)` — all 4 call sites pass 2 args correctly

### 5. Database Schema vs Code Alignment

| Table | Schema (db.py) | Queries (repository.py) | Status |
|-------|----------------|------------------------|--------|
| transactions | 26 columns + row_hash UNIQUE | All INSERT/SELECT match columns | Aligned |
| price_cache | PK(symbol, market, **price_date**) | get_cached_price, upsert_price use all 3 PK cols | Aligned |
| fx_rates | PK(date), usd_ils, source | get_fx_rate(date) → usd_ils | Aligned |
| tase_symbol_map | PK(ibi_id), td_symbol, yf_symbol, name | get_tase_symbol, upsert_tase_symbol match | Aligned |
| daily_portfolio_state | All columns defined | upsert_daily_state matches | Aligned |
| realized_trades | All columns defined | insert_realized_trade matches | Aligned |
| portfolio_snapshots | All columns defined | save_snapshot matches | Aligned |
| position_snapshots | FK to snapshots | save_snapshot matches | Aligned |
| import_log | 5 columns | log_import matches | Aligned |

Migration note: `db.py` includes a migration block (lines 155-168) that drops and recreates `price_cache` if `price_date` column is missing. This handles upgrades from the old schema correctly.

### 6. Test Coverage Gaps

| Module | Files | Functions | Has Tests | Risk Level |
|--------|-------|-----------|-----------|------------|
| classifiers/ibi_classifier.py | 1 | 25+ (21 tx types) | No | **Critical** |
| market/price_fetcher.py | 1 | 7 (API + cache) | No | **Critical** |
| portfolio/builder.py | 1 | 4 (core logic) | No | **Critical** |
| market/fx_fetcher.py | 1 | 6 (API + fallback) | No | **Critical** |
| database/repository.py | 1 | 20+ (CRUD) | No | High |
| portfolio/ingestion.py | 1 | 1 (7-step pipeline) | No | High |
| market/symbol_mapper.py | 1 | 6 (cache + API) | No | High |
| input/excel_reader.py | 1 | 3 (parse + hash) | No | High |
| dashboard/views/ | 2 | 2 (render funcs) | No | Medium |
| dashboard/components/ | 2 | 4 (charts + table) | No | Medium |
| models/ | 2 | 3 (dataclasses) | No | Low |
| **Total** | **31 files** | **100+ functions** | **0 tests** | **0% coverage** |

### 7. Undocumented Code (in code but not in MASTER_PLAN.md)

| Feature | File | Notes |
|---------|------|-------|
| `_display_label()` helper | charts.py:9-22 | Resolves TASE IBI IDs to ticker symbols for chart labels |
| `get_max_transaction_date()` | repository.py:47-53 | Returns latest transaction date for price reference |
| price_date parameter flow | price_fetcher → app → merged_view | Entire historical pricing pipeline undocumented |
| 3-tab layout (TASE/US/Merged) | app.py:175 | MASTER_PLAN still shows 2-tab layout |
| Sidebar CSS narrowing | app.py:26-39 | Custom CSS to reduce sidebar width |
| price_cache migration | db.py:155-168 | Auto-migration from old schema |

### 8. Minor Design Note

`TASE_PRICE_IN_AGOROT` in config.py (line 37) is defined as a module-level constant but used as **mutable runtime state** — `price_fetcher.py` sets it via `_cfg.TASE_PRICE_IN_AGOROT = True/False`. This works but is unusual for a "config" module.

---

## Recommendations

### Priority 1 — Documentation Update (MASTER_PLAN.md)
1. Update tab layout section: 2 tabs → 3 tabs (TASE, US, Merged)
2. Update price fetching section: live `/price` → historical `/time_series` with `price_date`
3. Update price_cache schema: add `price_date` to PK description
4. Update merged view: "current FX" → "historical FX for reference date"
5. Document the `_display_label()` chart label resolution
6. Fix EMCO → CMDR mapping reference
7. Document `get_max_transaction_date()` and the "prices as of" feature

### Priority 2 — Dead Code Cleanup (config.py)
Remove 8 unused constants from `src/config.py`:
- Lines 19-21: `PRICE_TTL_US_SEC`, `PRICE_TTL_TASE_SEC` (+ comment)
- Lines 23-26: `OPTION_SYMBOL_PATTERN`, `US_TICKER_SYMBOL_PATTERN`, `TASE_NUMERIC_PATTERN` (+ comment)
- Lines 28-34: `PHANTOM_SYMBOL_PREFIXES`, `PHANTOM_SYMBOLS`, `PHANTOM_NAME_KEYWORDS` (+ comment)

### Priority 3 — Test Infrastructure
Start with the 4 critical modules:
1. `ibi_classifier.py` — test all 21 transaction types + phantom detection
2. `price_fetcher.py` — mock API responses, test cache, test agorot normalization
3. `builder.py` — test position aggregation, realized P&L, multi-currency
4. `fx_fetcher.py` — mock API, test fallback chain

### Priority 4 — Minor Improvements
- Consider moving `TASE_PRICE_IN_AGOROT` out of config.py into price_fetcher.py as a module-level variable (it's runtime state, not configuration)
- Add a `README.md` for the Portfolio_Dashboard directory
