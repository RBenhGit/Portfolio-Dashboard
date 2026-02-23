# Project Re-Evaluation Report

**Date:** 2026-02-23
**Focus:** Full Project (post Statistics-tab addition, v2.0.0)

## Executive Summary

The codebase is well-aligned with its documentation after the recent 6-tab update. Three minor documentation issues were found and fixed during this evaluation (stale file references, duplicate task numbering, stale db.py comment). Two substantive issues remain: (1) MASTER_PLAN.md contains incorrect stock-split pseudocode, and (2) `TASE_PRICE_IN_AGOROT` is documented but never implemented as a config flag. The project has **zero test coverage** across all 85 functions and 21 modules.

---

## Findings

### Documentation Accuracy

| Area | Doc Says | Code Does | Status |
|------|----------|-----------|--------|
| Number of tabs | 6 (README, MASTER_PLAN) | 6 in `app.py` | ✅ Match |
| Tab order | Statistics, TASE, US, Merged, Options, Performance | Same in `app.py` lines 178-180 | ✅ Match |
| Database tables | 11 (README, MASTER_PLAN, db.py) | 11 in `db.py` CREATE TABLE statements | ✅ Match |
| Transaction types | 21 (README, MASTER_PLAN) | 21 in `ibi_classifier.py` TYPE_MAP | ✅ Match |
| Statistics tab signature | `render(portfolio, prices, price_date)` | `render(portfolio, prices, price_date="")` | ✅ Match |
| Performance metrics | CAGR, Sharpe, Max Drawdown, Total Return | All 4 in `performance_metrics.py` | ✅ Match |
| Benchmark names | S&P 500, TA-125 | `BENCHMARKS` dict in `benchmark_fetcher.py` | ✅ Match |
| FX fallback chain | repository → fx_fetcher → 3.7 | Same in `statistics_view.py`, `merged_view.py` | ✅ Match |
| Stock split algorithm | MASTER_PLAN: `ratio = qty_abs / pos.quantity` | Code: `ratio = (pos.quantity + qty_abs) / pos.quantity` | ⚠️ Mismatch |
| Stock split description | README: `new_quantity = current + added` | Code: `pos.quantity = pos.quantity * ratio` (equivalent result) | ✅ Match |
| `TASE_PRICE_IN_AGOROT` flag | MASTER_PLAN: "set a config flag" | Not in `config.py`; agorot ÷100 is hardcoded in classifier | ⚠️ Not implemented |
| Price data sources | Twelvedata primary + yfinance fallback | Both in `price_fetcher.py`, `fx_fetcher.py` | ✅ Match |
| WAL mode | Documented in README | `PRAGMA journal_mode=WAL` in `db.py` line 11 | ✅ Match |
| Dedup by row_hash | `INSERT OR IGNORE` on `row_hash` | `repository.py` uses this pattern | ✅ Match |

### Undocumented Code

| Code | Location | Notes |
|------|----------|-------|
| Stabilization detection (>10% daily change skip) | `statistics_view.py`, `performance_view.py` | Not mentioned in README or MASTER_PLAN |
| Option short-sell orphan skip logic | `builder.py:148-156` | Builder silently skips orphan option expiry credits; not documented |
| `_EPS = 1e-9` epsilon constant | `builder.py` | Floating-point guard; internal detail, low priority |

### Dead References

| Reference | Location | Status |
|-----------|----------|--------|
| `Project_ReEvaluation_2026-02-20.md` | Previously in README and MASTER_PLAN | ✅ Fixed during this evaluation |
| `TASE_PRICE_IN_AGOROT` config flag | MASTER_PLAN lines 41, 648 | ⚠️ Documented but never implemented; agorot conversion is hardcoded |

### Configuration Alignment

| Variable | `.env.template` | `config.py` | Code Usage | Status |
|----------|-----------------|-------------|------------|--------|
| `TWELVEDATA_API_KEY` | ✅ Present | `os.getenv("TWELVEDATA_API_KEY", "")` | `price_fetcher.py`, `fx_fetcher.py`, `symbol_mapper.py` | ✅ Match |
| `YFINANCE_ENABLED` | ✅ Present | `os.getenv("YFINANCE_ENABLED", "true")` | `price_fetcher.py`, `fx_fetcher.py` | ✅ Match |
| `BASE_DIR` | N/A (computed) | `Path(__file__).parent.parent` | Used for `EXCEL_PATH`, `DB_PATH` | ✅ OK |
| `EXCEL_PATH` | N/A (derived) | `BASE_DIR / "Trans_Input" / "Transactions_IBI.xlsx"` | `excel_reader.py`, `ingestion.py` | ✅ OK |
| `DB_PATH` | N/A (derived) | `BASE_DIR / "data" / "portfolio.db"` | `db.py` | ✅ OK |

No environment variables are used in code but missing from `.env.template`.

### Constants & Weights Verification

| Constant | Documented Value | Code Value | File:Line | Status |
|----------|-----------------|------------|-----------|--------|
| Split ratio formula | `qty_abs / pos.quantity` (MASTER_PLAN line 412) | `(pos.quantity + qty_abs) / pos.quantity` | `builder.py:160` | ⚠️ Doc wrong |
| Agorot divisor | ÷100 (README, MASTER_PLAN) | `/ 100` in `ibi_classifier.py` | `ibi_classifier.py` | ✅ Match |
| FX fallback rate | 3.7 (multiple docs) | `fx = 3.7` | `statistics_view.py:33`, `merged_view.py` | ✅ Match |
| Stabilization threshold | Not documented | `0.10` (10%) | `statistics_view.py:214`, `performance_view.py:42` | ℹ️ Undocumented |

### Test Coverage Gaps

| Module/Feature | Has Tests | Notes |
|----------------|-----------|-------|
| `src/config.py` | ❌ | No tests |
| `src/models/transaction.py` | ❌ | No tests |
| `src/models/position.py` | ❌ | No tests |
| `src/input/excel_reader.py` | ❌ | Critical — Hebrew parsing, agorot normalization |
| `src/classifiers/ibi_classifier.py` | ❌ | Critical — 21 transaction type mappings |
| `src/market/price_fetcher.py` | ❌ | 7 functions, API integration |
| `src/market/fx_fetcher.py` | ❌ | 7 functions, API integration |
| `src/market/symbol_mapper.py` | ❌ | 6 functions, TASE ID resolution |
| `src/market/benchmark_fetcher.py` | ❌ | 2 functions |
| `src/portfolio/builder.py` | ❌ | **Most critical** — 5 functions, all portfolio logic |
| `src/portfolio/ingestion.py` | ❌ | Pipeline orchestration |
| `src/database/db.py` | ❌ | Schema creation, migrations |
| `src/database/repository.py` | ❌ | 26 functions, all data access |
| `src/dashboard/components/charts.py` | ❌ | 3 functions |
| `src/dashboard/components/position_table.py` | ❌ | 3 functions |
| `src/dashboard/components/performance_metrics.py` | ❌ | 4 functions (CAGR, Sharpe, etc.) |
| `src/dashboard/views/statistics_view.py` | ❌ | New tab, 1 render function |
| `src/dashboard/views/portfolio_view.py` | ❌ | 1 render function |
| `src/dashboard/views/merged_view.py` | ❌ | 2 functions |
| `src/dashboard/views/options_view.py` | ❌ | 2 functions |
| `src/dashboard/views/performance_view.py` | ❌ | 1 render function |

**Summary:** 0 test files, 0% coverage across 85 functions in 21 modules.

---

## Recommendations

### Priority 1 — Fix Documentation Errors

1. **Fix stock split pseudocode in MASTER_PLAN.md** (line 412): Change `ratio = tx.share_quantity_abs / pos.quantity` to `ratio = (pos.quantity + tx.share_quantity_abs) / pos.quantity` to match actual `builder.py` implementation.

2. **Remove or update `TASE_PRICE_IN_AGOROT` references** in MASTER_PLAN.md (lines 41, 648): The agorot ÷100 conversion is hardcoded in `ibi_classifier.py`, not controlled by a config flag. Either remove the reference or document the actual behavior.

### Priority 2 — Add Test Coverage

3. **Start with `builder.py` tests** — the sequential portfolio build is the core algorithm. Test buy/sell/split/deposit/option flows with known inputs.
4. **Add `ibi_classifier.py` tests** — verify all 21 transaction type mappings, phantom detection, and agorot normalization.
5. **Add `repository.py` tests** — CRUD operations with an in-memory SQLite database.
6. **Add `performance_metrics.py` tests** — pure math functions (CAGR, Sharpe, Max Drawdown) are easy to unit test.

### Priority 3 — Document Implicit Behaviors

7. **Document the stabilization detection algorithm** — the 10% daily-change threshold used to skip the initial build-up period in performance calculations.
8. **Document orphan option expiry skip** — `builder.py` silently skips expiry credits for options with no prior short position.

---

*Generated by project re-evaluation on 2026-02-23.*
