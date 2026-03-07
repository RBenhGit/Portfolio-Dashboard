# Project Re-Evaluation Report
**Date:** 2026-03-07
**Focus:** Full Project
**Branch:** main

## Executive Summary

The Portfolio Dashboard codebase is well-aligned with its documentation overall. Out of ~60 verification points checked, **5 documentation inaccuracies** were found and **all 5 have been fixed**. The most significant remaining gap is test coverage: 18 out of 22 modules have zero test coverage (only 4 modules tested). All documented constants, formulas, and architectural claims are accurate.

---

## Findings

### Documentation Accuracy

| Area | Doc Says | Code Does | Status |
|------|----------|-----------|--------|
| Number of tabs | 6 tabs: Statistics, Performance, TASE, US, Merged, Options | 6 tabs with exact names (app.py:177-179) | Match |
| Database tables | 12 tables | 12 tables confirmed (db.py:16-168) | Match |
| Transaction columns | "26 columns" (MASTER_PLAN.md) | 26 columns including `id` autoincrement (db.py:21-48) | Match |
| Chart functions | 9 Plotly functions | All 9 exist in charts.py | Match |
| Performance metrics | CAGR 365.25d, Sharpe 4%/√252/min30 | All constants exact (performance_metrics.py) | Match |
| Color theme | 7 semantic colors documented | All 7 match (theme.py) | Match |
| Transaction types | 21 types | All 21 implemented (ibi_classifier.py) | Match |
| Phantom detection | 999*, 99028, 5039813, 4 name patterns | All patterns present (ibi_classifier.py:5-10) | Match |
| Stock split formula | `ratio = (pos.quantity + qty_abs) / pos.quantity` | Exact match (builder.py:178) | Match |
| Option regex | `^[89]\d{7}$` | Exact match (ibi_classifier.py:14) | Match |
| TASE static map | "12 known stocks" (README:187) | 12 entries (symbol_mapper.py:23-36) | Match (fixed) |
| Option reorder prefixes | "starting with 8 or 9" (MASTER_PLAN:373) | `sym[:1] in ("8", "9")` — covers 80-99 (builder.py:37) | Match (fixed) |
| Market detection priority | Numeric ID first, then currency (MASTER_PLAN:480-484) | Numeric ID checked FIRST (symbol_mapper.py:48-54) | Match (fixed) |
| Test count | "91 tests" (README:298, MASTER_PLAN:100) | 91 unique test functions (99 with parametrized) | Match (fixed) |
| BaseClassifier methods | classify, detect_phantom, normalize_price | All 3 exist with correct signatures | Match |
| Ingestion pipeline | 7-step flow documented | All steps implemented (ingestion.py) | Match |
| Benchmark symbols | ^GSPC and ^TA125.TA | Exact match (benchmark_fetcher.py:9-12) | Match |
| FX fallback rate | 3.7 ILS/USD | 3.7 confirmed (builder.py:85) | Match |
| Stabilization threshold | 10% daily change | Confirmed in performance_view.py | Match |
| Agorot ÷100 | Hardcoded in base_classifier and price_fetcher | Confirmed (base_classifier.py:27-28, price_fetcher.py:176-181) | Match |
| Sidebar controls | 6 controls (API status, upload, last import, re-parse, refresh, DB info) | All present (app.py:86-154) | Match |

### Undocumented Code

| Code | File:Line | Notes |
|------|-----------|-------|
| `daily_portfolio_state` migration (adds market value columns) | db.py:183-188 | Adds `nis_market_value`, `usd_market_value`, `total_market_value_nis` — now documented in MASTER_PLAN schema and used for performance metrics |
| `_OPTION_NAME_RE` pattern for Hebrew options | symbol_mapper.py:20 | `^ת[A-Z]\d+M\d+-\d+$` — now documented in MASTER_PLAN:485 |
| 5 additional TASE stocks in static map | symbol_mapper.py:28-36 | RIMO, ILX, BOTI, MRIN, TCH.F139 — now documented as 12 stocks |
| `to_dict()` method on Transaction | models/transaction.py:42-69 | Exists but not documented |
| `to_snapshot_dict()` method on Position | models/position.py:27-41 | Exists but not documented |
| `from_dict()` classmethod on Position | models/position.py:43-57 | Reconstructs Position from dict (used by fast-load cache) |
| Position `average_cost` as @property | models/position.py:23-25 | Computed property, not stored field |
| Fast-load cache functions | repository.py:362-432 | `save_portfolio_current()`, `load_portfolio_current()`, `is_portfolio_stale()` |
| `portfolio_current` table | db.py:163-166 | Fast-load cache table for serialized build result |
| Cache check in `_get_portfolio()` | app.py:74-77 | Checks staleness before falling back to full build |

### Dead References

| Reference | Location | Status |
|-----------|----------|--------|
| `docs/2000_api_guide_eng.pdf` | README:297, MASTER_PLAN:99 | Not found by glob — may exist but was not committed or is gitignored |
| `portfolio/ingestion.py` missing from MASTER_PLAN file structure | MASTER_PLAN:109 | File exists at `src/portfolio/ingestion.py` but MASTER_PLAN project structure section omits it |
| MASTER_PLAN Implementation Order Tab numbering | MASTER_PLAN:781-786 | Claims portfolio_view = Tab 2-3, merged = Tab 4, options = Tab 5, performance = Tab 6, statistics = Tab 1 — actual tabs are reordered |

### Configuration Alignment

| Variable | .env.example | config.py | Code Usage | Status |
|----------|-------------|-----------|------------|--------|
| `TWELVEDATA_API_KEY` | `your_key_here` | `os.getenv("TWELVEDATA_API_KEY", "")` (line 15) | price_fetcher.py, fx_fetcher.py | Match |
| `YFINANCE_ENABLED` | `true` | `os.getenv("YFINANCE_ENABLED", "true").lower() == "true"` (line 16) | price_fetcher.py | Match |
| `BASE_DIR` | N/A (computed) | `Path(__file__).parent.parent` (line 10) | Throughout | Match |
| `EXCEL_PATH` | N/A (hardcoded) | `"Trans_Input/Transactions_IBI.xlsx"` (line 11) | excel_reader.py, app.py | Match |
| `DB_PATH` | N/A (hardcoded) | `"data/portfolio.db"` (line 12) | db.py | Match |

No missing environment variables. No config used in code but absent from `.env.example`.

### Constants & Weights Verification

| Constant | Documented Value | Code Value | File:Line | Status |
|----------|-----------------|------------|-----------|--------|
| CAGR days/year | 365.25 | 365.25 | performance_metrics.py:27 | Match |
| Risk-free rate | 4% (0.04) | 0.04 | performance_metrics.py:40 | Match |
| Sharpe annualization | √252 | √252 | performance_metrics.py:57 | Match |
| Sharpe min points | 30 | 30 | performance_metrics.py:45 | Match |
| Rolling Sharpe window | 60 days | 60 | charts.py:305 (param) | Match |
| Stabilization threshold | 10% | 0.10 | performance_view.py:53 | Match |
| Agorot conversion | ÷100 | `/100.0` | base_classifier.py:28 | Match |
| Agorot detection threshold | >500 | >500 | price_fetcher.py:176 | Match |
| Donut hole size | 35% | 0.35 | charts.py:28 (param) | Match |
| Profit color | #10B981 | #10B981 | theme.py:19 | Match |
| Loss color | #EF4444 | #EF4444 | theme.py:21 | Match |
| Accent color | #6366F1 | #6366F1 | theme.py:28 | Match |
| S&P 500 color | #F59E0B | #F59E0B | theme.py:41 | Match |
| TA-125 color | #EC4899 | #EC4899 | theme.py:42 | Match |
| Background | #FAFBFE | #FAFBFE | theme.py:6 | Match |
| Text primary | #1E293B | #1E293B | theme.py:14 | Match |

### Test Coverage Gaps

| Module/Feature | Has Tests | Notes |
|----------------|-----------|-------|
| src/classifiers/ibi_classifier.py | Yes (37 tests) | test_classifier.py — all 21 types covered |
| src/portfolio/builder.py | Yes (10 tests) | test_builder.py — buys, sells, splits, options, cash |
| src/dashboard/components/performance_metrics.py | Yes (20 tests) | test_performance_metrics.py — CAGR, Sharpe, drawdown |
| src/database/repository.py | Yes (33 tests) | test_repository.py — all CRUD operations |
| src/config.py | **No** | No tests |
| src/input/excel_reader.py | **No** | Hebrew parsing, sorting, hashing untested |
| src/classifiers/base_classifier.py | **No** | ABC + normalize_price untested directly |
| src/market/symbol_mapper.py | **No** | Market detection, is_option, TASE resolution untested |
| src/market/price_fetcher.py | **No** | Twelvedata/yfinance integration untested |
| src/market/fx_fetcher.py | **No** | FX rate fetching untested |
| src/market/benchmark_fetcher.py | **No** | Benchmark caching untested |
| src/portfolio/ingestion.py | **No** | Full pipeline untested |
| src/database/db.py | **No** | Schema creation untested directly |
| src/dashboard/theme.py | **No** | Color constants untested |
| src/dashboard/styles.py | **No** | CSS and HTML helpers untested |
| src/dashboard/components/charts.py | **No** | 9 Plotly chart functions untested |
| src/dashboard/components/position_table.py | **No** | HTML table rendering untested |
| src/dashboard/views/* (5 files) | **No** | All 5 view files untested |

**Summary: 4/22 modules tested (18%). Docs now correctly state 91 tests.**

---

## Recommendations

### ~~Priority 1: Fix Documentation Inaccuracies~~ — DONE

All 5 documentation inaccuracies have been fixed:
1. ~~README.md: "7 known stocks" → "12 known stocks"~~ Done
2. ~~README.md + MASTER_PLAN.md: "88 tests" → "91 tests"~~ Done
3. ~~MASTER_PLAN.md: option prefixes "83/84/85" → "starting with 8 or 9"~~ Done
4. ~~MASTER_PLAN.md: market detection priority reordered to match code~~ Done
5. ~~Insufficient_Shares_Investigation: `86` prefix sub-issue marked as fixed~~ Done

### Priority 2: Document Undocumented Features

1. ~~**MASTER_PLAN.md schema** — Add the `daily_portfolio_state` migration columns (`nis_market_value`, `usd_market_value`, `total_market_value_nis`)~~ Done — columns already in MASTER_PLAN schema (lines 268-270) and now documented in performance-tab-why-how-what.md
2. **MASTER_PLAN.md file structure** — Add `src/portfolio/ingestion.py` which is missing from the project structure diagram

### Priority 3: Verify Dead References

3. **docs/2000_api_guide_eng.pdf** — Confirm this file exists; if not, remove references from README and MASTER_PLAN

### Priority 4: Expand Test Coverage

4. **High-value untested modules** — `symbol_mapper.py` (market detection logic), `excel_reader.py` (data ingestion boundary), and `ingestion.py` (full pipeline) are the most impactful gaps
5. **Integration test** — No end-to-end test exists that runs the full pipeline from Excel → DB → builder → dashboard rendering
