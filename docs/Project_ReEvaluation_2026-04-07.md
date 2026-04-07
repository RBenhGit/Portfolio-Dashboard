# Project Re-Evaluation Report

**Date:** 2026-04-07
**Focus:** Full Project
**Previous Reports:** 2026-03-08 (full project), 2026-04-02 (options module)

## Executive Summary

The project's core logic remains solid — all constants, formulas, charts, and database schema verified as matching. Since the last full re-evaluation (2026-03-08), 16 new tests were added (88→104), the `monthly_returns_heatmap` dead code was removed, and test_symbol_mapper.py was introduced. However, **the Cash Flow tab (Tab 7)** added in late March was never reflected in README.md, causing README to still say "6 tabs" when there are 7. The `_KNOWN_TASE_MAP` grew from 12→15 entries without doc updates. CLAUDE.md still lists only 8 of 12 database tables. USER_GUIDE.md has internal inconsistencies (says "88 tests" on line 55 but "104 tests" on line 1036; says "6 tabs" in architecture diagram but "7 Dashboard Tabs" in the feature table). The deprecated `applymap()` from the options report was fixed. The `.env.template` file referenced in the original evaluation request doesn't exist — the actual file is `.env.example`.

---

## Findings

### Documentation Accuracy

| # | Area | Doc Says | Code Does | Status |
|---|------|----------|-----------|--------|
| 1 | README.md — tab count | "6 interactive tabs" (lines 3, 120, 173, 304) | **7 tabs** in `app.py:181-182` (Statistics, Performance, TASE, US, Merged, Options, Cash Flow) | **Mismatch** |
| 2 | README.md — Cash Flow tab | Not mentioned anywhere | Fully implemented: `cashflow_view.py` (Tab 7), imported in `app.py:48` | **Missing** |
| 3 | README.md — Dashboard Tabs table | "### Dashboard Tabs (6)" lists only 6 | Should list 7 including Cash Flow | **Missing** |
| 4 | README.md — Architecture diagram | "Streamlit Dashboard (app.py) — 6 tabs" | 7 tabs | **Mismatch** |
| 5 | README.md — Data Flow | "Render 6 tabs" (line 173), Tab 6 is last | Tab 7 (Cash Flow) exists | **Missing** |
| 6 | README.md — Project Structure | `app.py # Streamlit entry point (6 tabs)`, no `cashflow_view.py` listed | 7 tabs, `cashflow_view.py` exists | **Missing** |
| 7 | README.md — TASE static map | "static map (14 known stocks)" (line 194) | **15 entries** in `_KNOWN_TASE_MAP` (`symbol_mapper.py:26-42`) | **Mismatch** |
| 8 | CLAUDE.md — database tables | Lists 8 tables: transactions, price_cache, fx_rates, daily_portfolio_state, realized_trades, portfolio_current, tase_symbol_map, benchmark_cache | **12 tables** in `db.py`. Missing: metadata, portfolio_snapshots, position_snapshots, import_log | **Incomplete** |
| 9 | CLAUDE.md — TASE static map | "14 known stocks" | **15 entries** in `_KNOWN_TASE_MAP` | **Mismatch** |
| 10 | MASTER_PLAN.md — file structure | `app.py # Streamlit entry point (6 tabs)` (line 92) | 7 tabs | **Mismatch** |
| 11 | USER_GUIDE.md — test count (line 55) | "4 test files, 88 tests" | **5 test files, 104 tests** | **Mismatch** |
| 12 | USER_GUIDE.md — test count (line 1036) | "104 tests across 5 files" | Correct (104 tests, 5 files) | Match |
| 13 | USER_GUIDE.md — architecture diagram (line 143) | "Streamlit Dashboard (6 tabs)" | 7 tabs | **Mismatch** |
| 14 | USER_GUIDE.md — startup flow (line 155) | "Render 6 tabs" | 7 tabs | **Mismatch** |
| 15 | USER_GUIDE.md — key capabilities table (line 35) | "22 Transaction Types" | Code handles **21 types** + forex as special cases of existing types. Classifier says "all 21 transaction types" | **Mismatch** |
| 16 | Previous report (2026-03-08) — TASE map count | "12 static TASE entries... Match" | **15 entries** in current code | **Previous report was stale** |
| 17 | Previous report (2026-03-08) — test count | "88 tests collected by pytest" | **104 tests** now (16 new tests added since) | **Previous report stale** |
| 18 | CAGR formula (365.25 days/year) | All docs match | `performance_metrics.py:27` uses 365.25 | Match |
| 19 | Risk-free rate 4% fallback | All docs match | `performance_metrics.py` + `benchmark_fetcher.py` | Match |
| 20 | Sharpe √252 annualization | All docs match | `performance_metrics.py:64` | Match |
| 21 | Min 30 data points for Sharpe | All docs match | `performance_metrics.py:49` | Match |
| 22 | _EPS = 0.001 | MASTER_PLAN matches | `builder.py:19` | Match |
| 23 | 12 SQLite tables | README, MASTER_PLAN match | `db.py` has 12 CREATE TABLE statements | Match |
| 24 | WAL mode enabled | All docs match | `db.py:11` | Match |
| 25 | transactions table 26 columns | README matches | `db.py:22-47` has 26 columns | Match |
| 26 | 8 Plotly chart functions | README, CLAUDE.md match | `charts.py` has exactly 8 functions | Match |
| 27 | All chart height values | README matches | All 8 heights verified (380, auto, 450, 400, 420, 250, 350, 300) | Match |
| 28 | All color hex values | README matches | All 7 theme colors verified in `theme.py` | Match |
| 29 | ibi_dark Plotly template | README matches | `theme.py:83` registers "ibi_dark" template | Match |
| 30 | Stabilization threshold 10% | All docs match | `performance_view.py:30` uses 0.10 | Match |
| 31 | Rolling Sharpe window 60d | All docs match | `charts.py` rolling_sharpe_chart defaults to 60 | Match |
| 32 | S&P 500 = ^GSPC | All docs match | `benchmark_fetcher.py` | Match |
| 33 | TA-125 = ^TA125.TA | All docs match | `benchmark_fetcher.py` | Match |
| 34 | Option detection regex | USER_GUIDE matches | `symbol_mapper.py:21` `^[89]\d{7}$` | Match |
| 35 | Option expiry reordering | CLAUDE.md, README match | `builder.py:24-41` correctly reorders | Match |
| 36 | Stock split handling (price=0 vs >0) | README, CLAUDE.md describe correctly | `ibi_classifier.py:136-146` differentiates split vs bonus | Match |
| 37 | is_portfolio_stale() behavior | README matches | `repository.py:413-438` compares built_at vs import_log | Match |
| 38 | Position.to_snapshot_dict() | README mentions | `position.py:29-43` exists and used in serialization | Match |
| 39 | Position.from_dict() | README mentions | `position.py:45-59` exists | Match |
| 40 | Deprecated applymap() | Options report flagged | **Fixed**: `options_view.py:92` now uses `.map()` | **Resolved** |

### Undocumented Code

| # | Item | Location | Description |
|---|------|----------|-------------|
| 1 | Cash Flow tab and view | `cashflow_view.py` + `app.py:209-210` | Full Tab 7 implementation. Documented in USER_GUIDE.md and MASTER_PLAN.md but **missing from README.md** |
| 2 | `twelvedata` pip package | `requirements.txt:8` | Listed as dependency but not in README tech stack table or MASTER_PLAN requirements section |
| 3 | 3 new TASE entries | `symbol_mapper.py:39-42` | ESLT (1081124), TCH.F34 (1145184), ATRY (1096106) added since last doc update |

### Dead References

| # | Document | Reference | Status |
|---|----------|-----------|--------|
| 1 | `performance-tab-why-how-what.md` | Error message "Portfolio has no positive values to display." | Still does not exist in code (unfixed from 2026-03-08 report) |

### Configuration Alignment

| Variable | .env.example | config.py | Code Usage | Status |
|----------|-------------|-----------|------------|--------|
| `TWELVEDATA_API_KEY` | `your_key_here` | `os.getenv("TWELVEDATA_API_KEY", "")` | price_fetcher, fx_fetcher, symbol_mapper | Match |
| `YFINANCE_ENABLED` | `true` | `os.getenv("YFINANCE_ENABLED", "true").lower() == "true"` | price_fetcher (yfinance fallback) | Match |
| `.env.template` | — | — | File does not exist; actual file is `.env.example` | N/A |

No undocumented environment variables found. All env vars used in code are present in `.env.example`.

### Constants & Weights Verification

| Constant | Documented Value | Code Value | File:Line | Status |
|----------|-----------------|------------|-----------|--------|
| CAGR days/year | 365.25 | 365.25 | performance_metrics.py:27 | Match |
| Risk-free rate fallback | 4% annual | 0.04 | benchmark_fetcher.py | Match |
| Sharpe annualization | √252 | np.sqrt(252) | performance_metrics.py:64 | Match |
| Min Sharpe points | 30 | 30 | performance_metrics.py:49 | Match |
| _EPS threshold | 0.001 | 0.001 | builder.py:19 | Match |
| Stabilization threshold | 10% | 0.10 | performance_view.py:30 | Match |
| Rolling Sharpe window | 60 days | 60 | charts.py (rolling_sharpe_chart) | Match |
| Pie chart hole | 35% | 0.35 | charts.py:85 | Match |
| Pie chart height | 380px | 380 | charts.py:85 | Match |
| Treemap height | 450px | 450 | charts.py:171 | Match |
| Waterfall height | 400px | 400 | charts.py:212 | Match |
| Area chart height | 420px | 420 | charts.py:239 | Match |
| Drawdown height | 250px | 250 | charts.py:261 | Match |
| Monthly bar height | 350px | 350 | charts.py:289 | Match |
| Rolling Sharpe height | 300px | 300 | charts.py:330 | Match |
| PROFIT color | #10B981 | #10B981 | theme.py:19 | Match |
| LOSS color | #EF4444 | #EF4444 | theme.py:21 | Match |
| ACCENT_PRIMARY | #6366F1 | #6366F1 | theme.py:28 | Match |
| BM_SP500 | #F59E0B | #F59E0B | theme.py:41 | Match |
| BM_TA125 | #EC4899 | #EC4899 | theme.py:42 | Match |
| BG_PRIMARY | #FAFBFE | #FAFBFE | theme.py:6 | Match |
| TEXT_PRIMARY | #1E293B | #1E293B | theme.py:14 | Match |
| _KNOWN_TASE_MAP entries | 14 (README, CLAUDE.md) | **15** | symbol_mapper.py:26-42 | Mismatch |
| _KNOWN_US_NUMERIC_IDS | Exists (CLAUDE.md) | 2 entries (GOGL, SMED) | symbol_mapper.py:47-50 | Match |
| _HEBREW_ABBREVS | Exists (README) | 8 entries | symbol_mapper.py:155-164 | Match |

### Test Coverage

**Actual: 104 tests across 5 files** (verified via `pytest --collect-only`)

| Test File | Test Count | Coverage |
|-----------|-----------|----------|
| `test_builder.py` | 12 | Portfolio build: buy/sell/split/deposit, option expiry, cash |
| `test_classifier.py` | 29 | All 21 types, phantom detection, price normalization |
| `test_performance_metrics.py` | 20 | CAGR, Sharpe, max drawdown, cumulative returns |
| `test_repository.py` | 24 | All CRUD operations for all table types |
| `test_symbol_mapper.py` | 14 | is_option() regex, parse_option_expiry() date extraction |
| **Total** | **104** | |

#### Test Coverage Gaps

| Module/Feature | Has Tests | Notes |
|----------------|-----------|-------|
| `src/classifiers/ibi_classifier.py` | Yes (29) | All 21 types + phantoms + normalization |
| `src/portfolio/builder.py` | Yes (12) | Core flows, splits, options, cash |
| `src/dashboard/components/performance_metrics.py` | Yes (20) | All 4 metrics + edge cases |
| `src/database/repository.py` | Yes (24) | All CRUD operations |
| `src/market/symbol_mapper.py` | Yes (14) | **NEW since last report** — is_option + expiry parsing |
| `src/input/excel_reader.py` | **No** | Column mapping, date parsing, hashing untested |
| `src/market/price_fetcher.py` | **No** | Price fetching, agorot detection untested |
| `src/market/fx_fetcher.py` | **No** | FX rate fetching untested |
| `src/market/benchmark_fetcher.py` | **No** | Benchmark caching, risk-free rate fetch untested |
| `src/portfolio/ingestion.py` | **No** | End-to-end pipeline untested |
| `src/models/position.py` | Indirect | Used via builder/repository tests |
| Dashboard views (6 files) | **No** | UI layer — typical for Streamlit apps |
| `src/dashboard/components/charts.py` | **No** | Plotly rendering |
| `src/dashboard/components/position_table.py` | **No** | HTML table rendering |
| `src/dashboard/theme.py` | **No** | Pure constants |
| `src/dashboard/styles.py` | **No** | CSS/HTML helpers |
| `src/config.py` | **No** | Simple env var loader |

**Coverage: 5/23 modules tested (22%), 104 tests total**

---

## Comparison with Previous Reports

### Since 2026-03-08 Full Report

| Finding | Previous Status | Current Status |
|---------|----------------|----------------|
| Test count | 88 tests | **104 tests** (+16 new; test_symbol_mapper.py added) |
| monthly_returns_heatmap dead code | Dead code in charts.py | **Removed** (8 functions now, not 9) |
| _KNOWN_TASE_MAP entries | 12 entries | **15 entries** (+3: ESLT, TCH.F34, ATRY) |
| Cash Flow tab | Did not exist | **Fully implemented** (Tab 7) — but README not updated |
| Deprecated applymap() | Not flagged (added Apr 2) | **Fixed** — now uses .map() |
| `twelvedata` undocumented | Flagged | **Still undocumented** in README tech stack |
| perf-tab error message dead ref | Flagged | **Still present** in performance-tab-why-how-what.md |

### Since 2026-04-02 Options Report

| Finding | Previous Status | Current Status |
|---------|----------------|----------------|
| MASTER_PLAN tab numbers (items 1-3) | Flagged as wrong | **Still unfixed** — Tab 5 should be Tab 6 for Options, etc. |
| MASTER_PLAN wireframe (items 4-5) | Flagged as stale | **Still unfixed** |
| Deprecated applymap() | Flagged | **Fixed** |

---

## Recommendations

### Priority 1 — Fix README.md Cash Flow Gap (6 updates)

The README is the user-facing document and is the most stale:

1. **Line 3**: Change "delivers 6 interactive tabs" → "delivers 7 interactive tabs"
2. **Line 46**: Change "### Dashboard Tabs (6)" → "### Dashboard Tabs (7)", add Tab 7 row for Cash Flow
3. **Lines 120, 173, 304**: Update all "6 tabs" references to "7 tabs"
4. **Line 179**: Add Tab 7 entry to Data Flow section
5. **Lines 303-357**: Add `cashflow_view.py` to Project Structure listing
6. **Line 194**: Change "14 known stocks" → "15 known stocks"

### Priority 2 — Fix CLAUDE.md Gaps (2 updates)

7. **Line 29**: Replace partial table list (8 tables) with all 12: transactions, fx_rates, price_cache, metadata, portfolio_snapshots, position_snapshots, daily_portfolio_state, realized_trades, import_log, tase_symbol_map, benchmark_cache, portfolio_current
8. **Line 37**: Change "14 known stocks" → "15 known stocks" (or remove exact count since it changes)

### Priority 3 — Fix USER_GUIDE.md Internal Inconsistencies (3 updates)

9. **Line 55**: Change "4 test files, 88 tests" → "5 test files, 104 tests"
10. **Line 143**: Change "Streamlit Dashboard (6 tabs)" → "Streamlit Dashboard (7 tabs)"
11. **Line 155**: Change "Render 6 tabs" → "Render 7 tabs"

### Priority 4 — Fix MASTER_PLAN.md Stale References (3 updates)

12. **Line 92**: Change `app.py # Streamlit entry point (6 tabs)` → `(7 tabs)`
13. **Line 35 (Key Capabilities)**: Clarify "22 Transaction Types" → "21 transaction types (+ forex as special cases of buy/sell)" to match classifier's own documentation

### Priority 5 — Document `twelvedata` Package (1 update)

14. **README.md Tech Stack table**: Add `twelvedata` row (no version pin in requirements.txt)

### Priority 6 — Fix Stale Previous-Report Findings (1 update)

15. **performance-tab-why-how-what.md**: Remove reference to non-existent error message "Portfolio has no positive values to display." (unfixed since 2026-03-08)

### Priority 7 — Fix MASTER_PLAN.md Tab Numbers (from Options Report, still unfixed)

16. **MASTER_PLAN.md:809-811**: Fix tab numbers (TASE=Tab 3 not Tab 2, US=Tab 4 not Tab 3, Options=Tab 6 not Tab 5, Performance=Tab 2 not Tab 6)
17. **MASTER_PLAN.md:648-661**: Update wireframe to show merged options table with Currency column

### Priority 8 — Expand Test Coverage (optional)

18. **High-value targets**: `excel_reader.py` (date parsing, hashing), `ingestion.py` (end-to-end pipeline)
19. **Medium-value targets**: `price_fetcher.py` (agorot detection), `fx_fetcher.py` (gap filling), `benchmark_fetcher.py` (cache logic)
