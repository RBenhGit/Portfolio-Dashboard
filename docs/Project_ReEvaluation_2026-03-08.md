# Project Re-Evaluation Report

**Date:** 2026-03-08
**Focus:** Full Project
**Previous Report:** 2026-03-07 (superseded)

## Executive Summary

The project's core logic (classification, building, metrics, database) is well-documented and accurate — all 22+ constants and formulas verified as matching. However, the Performance tab has grown from 6 to 8 charts without documentation updates, the `monthly_returns_heatmap` function is dead code (defined but never called), several file:line references in docs are stale, and the test count in README (91) no longer matches reality (88). The previous report incorrectly flagged `2000_api_guide_eng.pdf` as a dead reference — it exists.

---

## Findings

### Documentation Accuracy

| # | Area | Doc Says | Code Does | Status |
|---|------|----------|-----------|--------|
| 1 | Performance tab chart count | "6 charts" (README, MASTER_PLAN, perf-tab doc) | 8 charts rendered (added US vs TASE invested capital, US vs TASE cumulative returns, market-value cumulative returns) | **Mismatch** |
| 2 | `monthly_returns_heatmap` | Listed as a feature in README, MASTER_PLAN, perf-tab doc | Function exists in charts.py:238 but is **never imported or called** from any view | **Dead Code** |
| 3 | Test count | "91 tests" (README:302) | 88 tests collected by pytest | **Mismatch** |
| 4 | Stabilization line ref (README) | `performance_view.py:46-56` | Actually at lines 24-34 (`_stable_start_filter`) | **Stale Ref** |
| 5 | Stabilization line ref (perf-tab doc) | `performance_view.py:35-47` | Actually at lines 24-34 | **Stale Ref** |
| 6 | Stabilization line ref (perf-tab doc) | `performance_view.py:53` for threshold | Actually line 30 | **Stale Ref** |
| 7 | Total Return line ref (perf-tab doc) | `performance_view.py:65` | Actually line 87 | **Stale Ref** |
| 8 | perf-tab doc algorithm code block | Shows "performance_view.py lines 46-56" | Function is at lines 24-34 | **Stale Ref** |
| 9 | perf-tab doc error state | "Portfolio has no positive values to display." | This message does NOT exist in performance_view.py | **Dead Doc** |
| 10 | Option expiry line ref (README) | `builder.py:21-51` | Actually lines 22-52 (off by 1) | **Minor** |
| 11 | db.py benchmark_cache line ref (perf-tab doc) | `db.py:153-159` | Actually lines 156-162 | **Stale Ref** |
| 12 | db.py daily_portfolio_state line ref (perf-tab doc) | `db.py:106-118` | Actually lines 106-121 | **Minor** |
| 13 | Previous report finding | Flagged `2000_api_guide_eng.pdf` as dead reference | File EXISTS at `docs/2000_api_guide_eng.pdf` | **Incorrect** |
| 14 | CAGR formula (365.25 days/year) | All docs match | `performance_metrics.py:27` | Match |
| 15 | Risk-free rate 4% | All docs match | `performance_metrics.py:40` | Match |
| 16 | Sharpe √252 annualization | All docs match | `performance_metrics.py:57` | Match |
| 17 | Min 30 data points for Sharpe | All docs match | `performance_metrics.py:45` | Match |
| 18 | _EPS = 0.001 | MASTER_PLAN matches | `builder.py:19` | Match |
| 19 | FX fallback 3.7 | MASTER_PLAN matches | `builder.py:85` | Match |
| 20 | 12 static TASE entries | README matches | `symbol_mapper.py:23-36` (12 entries) | Match |
| 21 | 21 transaction types | README matches | `ibi_classifier.py` handles all 21 | Match |
| 22 | 12 SQLite tables | README, MASTER_PLAN match | `db.py:20-167` (12 CREATE TABLE) | Match |
| 23 | WAL mode enabled | All docs match | `db.py:11` | Match |
| 24 | 9 Plotly chart functions | README matches | `charts.py` has 9 functions | Match |
| 25 | S&P 500 = ^GSPC | All docs match | `benchmark_fetcher.py:10` | Match |
| 26 | TA-125 = ^TA125.TA | All docs match | `benchmark_fetcher.py:11` | Match |
| 27 | All color hex values | README matches | `theme.py` all verified | Match |

### Undocumented Code

| # | Item | Location | Description |
|---|------|----------|-------------|
| 1 | US vs TASE invested capital chart | `performance_view.py:200-243` | New chart "Invested Capital — US vs TASE (base 100)" not in any doc |
| 2 | US vs TASE cumulative returns chart | `performance_view.py:245-292` | New chart "Cumulative Returns — US vs TASE (base 100)" not in any doc |
| 3 | Market-value cumulative returns chart | `performance_view.py:165-198` | New chart "Cumulative Returns vs Benchmarks (base 100)" using market value series, not documented |
| 4 | `twelvedata` pip package | `requirements.txt:8` | Listed as dependency but not mentioned in README tech stack table |
| 5 | Hebrew abbreviation expansion | `symbol_mapper.py:107-131` | `_HEBREW_ABBREVS` dict and `_clean_hebrew_name()` not documented in any doc |
| 6 | Disclaimer caption | `performance_view.py:307-309` | Explains difference between Invested Capital and Cumulative Returns charts |

### Dead References

| # | Document | Reference | Status |
|---|----------|-----------|--------|
| 1 | `performance-tab-why-how-what.md:213` | Error message "Portfolio has no positive values to display." | Message does not exist in code |
| 2 | `performance-tab-why-how-what.md:154` | "Monthly Returns Heatmap" listed as feature #7 | Function exists but is never called |
| 3 | `README.md:65` | `monthly_returns_heatmap()` listed in chart table | Function exists but is never called from any view |

### Dead Code

| # | Item | Location | Description |
|---|------|----------|-------------|
| 1 | `monthly_returns_heatmap()` | `charts.py:238-274` | Fully implemented (37 lines) but never imported or called from any view. Should either be used in performance_view.py or removed. |

### Configuration Alignment

| Variable | .env.example | config.py | Code Usage | Status |
|----------|-------------|-----------|------------|--------|
| `TWELVEDATA_API_KEY` | `your_key_here` | `os.getenv("TWELVEDATA_API_KEY", "")` | price_fetcher, fx_fetcher, symbol_mapper | Match |
| `YFINANCE_ENABLED` | `true` | `os.getenv("YFINANCE_ENABLED", "true").lower() == "true"` | price_fetcher (checked before yfinance fallback) | Match |

No missing environment variables found. All env vars used in code are present in `.env.example`.

### Constants & Weights Verification

| Constant | Documented Value | Code Value | File:Line | Status |
|----------|-----------------|------------|-----------|--------|
| CAGR days/year | 365.25 | 365.25 | performance_metrics.py:27 | Match |
| Risk-free rate | 4% annual | 0.04 | performance_metrics.py:40 | Match |
| Sharpe annualization | √252 | np.sqrt(252) | performance_metrics.py:57 | Match |
| Min Sharpe points | 30 | 30 | performance_metrics.py:45 | Match |
| _EPS threshold | 0.001 | 0.001 | builder.py:19 | Match |
| FX fallback rate | 3.7 ILS/USD | 3.7 | builder.py:85 | Match |
| Stabilization threshold | 10% | 0.10 | performance_view.py:30 | Match |
| Rolling Sharpe window | 60 days | 60 | charts.py:305 | Match |
| Pie chart hole | 35% | 0.35 | charts.py:51 | Match |
| Pie chart height | 380px | 380 | charts.py:56 | Match |
| Treemap height | 450px | 450 | charts.py:141 | Match |
| Waterfall height | 400px | 400 | charts.py:183 | Match |
| Area chart height | 420px | 420 | charts.py:209 | Match |
| Drawdown height | 250px | 250 | charts.py:231 | Match |
| Monthly bar height | 350px | 350 | charts.py:298 | Match |
| Rolling Sharpe height | 300px | 300 | charts.py:339 | Match |
| PROFIT color | #10B981 | #10B981 | theme.py:19 | Match |
| LOSS color | #EF4444 | #EF4444 | theme.py:21 | Match |
| ACCENT_PRIMARY | #6366F1 | #6366F1 | theme.py:28 | Match |
| BM_SP500 | #F59E0B | #F59E0B | theme.py:41 | Match |
| BM_TA125 | #EC4899 | #EC4899 | theme.py:42 | Match |
| BG_PRIMARY | #FAFBFE | #FAFBFE | theme.py:6 | Match |
| TEXT_PRIMARY | #1E293B | #1E293B | theme.py:14 | Match |

### Test Coverage Gaps

| Module/Feature | Has Tests | Notes |
|----------------|-----------|-------|
| `src/classifiers/ibi_classifier.py` | Yes (37 tests) | All 21 types covered |
| `src/portfolio/builder.py` | Yes (10 tests) | Core flows, splits, options, cash |
| `src/dashboard/components/performance_metrics.py` | Yes (20 tests) | All 4 metrics + edge cases |
| `src/database/repository.py` | Yes (21 tests) | All CRUD operations |
| `src/input/excel_reader.py` | **No** | Column mapping, date parsing, hashing untested |
| `src/market/symbol_mapper.py` | **No** | Symbol resolution chain, option detection untested |
| `src/market/price_fetcher.py` | **No** | Price fetching, agorot detection untested |
| `src/market/fx_fetcher.py` | **No** | FX rate fetching untested |
| `src/market/benchmark_fetcher.py` | **No** | Benchmark caching logic untested |
| `src/portfolio/ingestion.py` | **No** | End-to-end pipeline untested |
| `src/models/position.py` | Indirect only | Used in builder tests but no direct tests |
| `src/database/db.py` | Indirect only | Schema used via test fixtures |
| Dashboard views (5 files) | **No** | UI layer — typical for Streamlit apps |
| `src/dashboard/theme.py` | **No** | Pure constants |
| `src/dashboard/styles.py` | **No** | CSS/HTML helpers |
| `src/dashboard/components/charts.py` | **No** | Plotly rendering |
| `src/dashboard/components/position_table.py` | **No** | HTML table rendering |

**Coverage: 4/22 modules tested (18%), 88 tests total**

---

## Recommendations

### Priority 1 — Fix Documentation Drift (6 items)

1. **Update performance tab chart count** in README.md, MASTER_PLAN.md, and performance-tab-why-how-what.md from "6 charts" to "8 charts" (or current actual count). Document the 3 new charts: market-value cumulative returns, US vs TASE invested capital, US vs TASE cumulative returns.
2. **Fix test count** in README.md from "91 tests" to "88 tests".
3. **Fix stale line references** in README.md (`performance_view.py:46-56` → `24-34`, `builder.py:21-51` → `22-52`).
4. **Fix stale line references** in performance-tab-why-how-what.md (6 stale references listed above).
5. **Remove non-existent error message** "Portfolio has no positive values to display." from performance-tab-why-how-what.md:213.
6. **Add `twelvedata` package** to README tech stack table.

### Priority 2 — Resolve Dead Code (1 item) — DONE

7. **`monthly_returns_heatmap()`** — Removed from `charts.py` and all doc references (README, MASTER_PLAN, perf-tab doc). Chart count updated from 9→8 in README, from "6 charts"→"8 charts" in perf-tab doc.

### Priority 3 — Document New Features (2 items) — DONE

8. **Hebrew abbreviation expansion** — Documented in README under TASE Symbol Resolution.
9. **Invested Capital vs Cumulative Returns methodology** — Documented in perf-tab doc: Features list updated with all 8 charts and the disclaimer caption; Outputs table updated; intro paragraph rewritten to explain the two chart families.

### Priority 4 — Expand Test Coverage (optional)

10. **High-value targets:** `excel_reader.py` (date parsing, hashing), `symbol_mapper.py` (option detection, resolution chain), `ingestion.py` (end-to-end pipeline).
11. **Medium-value:** `price_fetcher.py` (agorot detection), `fx_fetcher.py` (gap filling), `benchmark_fetcher.py` (cache logic).

### Priority 5 — Correct Previous Report Error

12. The 2026-03-07 report incorrectly flagged `docs/2000_api_guide_eng.pdf` as a dead reference. The file exists. This report supersedes the previous one.
