# Project Re-Evaluation Report

**Date:** 2026-06-12
**Focus:** Full Project
**Previous Reports:** 2026-03-08 (full, removed), 2026-04-02 (options module), 2026-04-07 (full, replaced by this report)

> **Resolution status (2026-06-12, same day):** All recommendations below were applied.
> `waterfall_pnl()` removed; tab order fixed in all 4 docs; resolution chain + structure
> trees updated; Twelvedata agorot heuristic documented; `updated_at` added to schema doc;
> analysis JSONs deleted; `output/` + verification `.xlsx` gitignored; `tests/verification_data/README.md`
> added. New tests added for `price_fetcher`, `excel_reader`, and the ingestion pipeline —
> suite is now **145 tests / 9 files** (numbers in the body of this report predate that).

## Executive Summary

The core engine remains fully consistent with documentation — all constants, formulas, schema details, classifier types, and theme values verified exact. The drift since 2026-04-07 comes from two recent changes that the docs only partially absorbed: (1) the **Cash Flow tab was moved from Tab 7 to Tab 3** (commit `4fada7a`), but README.md, CLAUDE.md, MASTER_PLAN.md, and USER_GUIDE.md all still describe the old order; (2) the **TASE website API resolver** (`src/market/tase_api.py`) was added to the symbol-resolution chain and is documented in CLAUDE.md, but README.md still describes the old chain ("static map (15 known stocks) → Twelvedata `symbol_search` → None") — the map now has **16 entries** and the TASE API sits before Twelvedata. Test count grew from 104 to **116 tests across 6 files** (new `test_tase_api.py`, +5 classifier tests); all docs still say 104. Several one-off analysis artifacts (`scripts/`, `output/`, three `*_analysis.json` files, `tests/verification_data/`) sit untracked at the repo root, referenced by nothing.

---

## Findings

### Documentation Accuracy

| # | Area | Doc Says | Code Does | Status |
|---|------|----------|-----------|--------|
| 1 | Tab order — README.md (Dashboard Tabs table, Data Flow), CLAUDE.md (Architecture), MASTER_PLAN.md (wireframes :528, :600), USER_GUIDE.md (:37, :86-90) | Cash Flow is Tab 7, last; TASE=3, US=4, Merged=5, Options=6 | `app.py:181-183`: Statistics, Performance, **Cash Flow (Tab 3)**, TASE (4), US (5), Merged (6), Options (7) — commit `4fada7a` | **Mismatch** |
| 2 | MASTER_PLAN.md:520 — section heading | "Dashboard Layout (Streamlit — 6 Tabs)" | 7 tabs | **Mismatch** (carried over from 2026-04-07 report, still unfixed) |
| 3 | README.md:196 — TASE symbol resolution chain | "runtime cache → DB cache → static map (15 known stocks) → Twelvedata `symbol_search` API → fallback to None" | `symbol_mapper.py:109-164`: runtime cache → DB cache → static map (**16** entries) → **TASE website API (`tase_api.lookup_security()`)** → Twelvedata search → None | **Mismatch** |
| 4 | MASTER_PLAN.md — Symbol Mapper section (~:508) | No mention of `tase_api.py`; resolution implied via Twelvedata only | TASE website API is the primary network resolver (`symbol_mapper.py:140-148`) | **Missing** |
| 5 | CLAUDE.md — resolution chain | "runtime cache → DB → `_KNOWN_TASE_MAP` → TASE website API (`tase_api.py`, no key needed) → Twelvedata search" | Matches `symbol_mapper.py:109-164` exactly | Match |
| 6 | Test count — README.md:315 ("104 tests"), MASTER_PLAN.md:102, USER_GUIDE.md:42 | 104 tests, 5 files | **116 tests, 6 files** (`pytest --collect-only`): builder 12, classifier **34**, performance_metrics 20, repository 24, symbol_mapper 14, **tase_api 12 (new)** | **Mismatch** |
| 7 | README.md / MASTER_PLAN.md — Project Structure | No `src/market/tase_api.py`, no `tests/test_tase_api.py`, no `config/initial_positions.json` | All three exist; `builder.py:44-104` loads initial positions (MSFT, IBM, JPM, TSLA) at build start | **Missing** |
| 8 | README.md — Pre-Transfer Phantom Shares: "14 symbols are affected" | Phantom auto-fill still exists (`builder.py:376-384`), but `config/initial_positions.json` now seeds 4 US positions before the pass, which changes which symbols still need phantom fills | **Needs Review** — count likely stale |
| 9 | README.md — chart table: `pnl_bar()` height "auto" | `charts.py:119`: `height=max(300, len(syms) * 30 + 80)` — dynamic, not Plotly auto | Needs Review (minor wording) |
| 10 | README.md / USER_GUIDE.md — `waterfall_pnl()` listed among the 8 charts | Function exists (`charts.py:175-216`, 400px) but is **not imported or called by any view** — dead code | **Mismatch** (docs imply it's in use) |
| 11 | MASTER_PLAN.md — `tase_symbol_map` schema | Columns: ibi_id, td_symbol, yf_symbol, name | `db.py:148-154` also has `updated_at` (set in `repository.py:362`) | **Incomplete** |
| 12 | MASTER_PLAN.md:511-513 — market detection rule 3: "₪ + 1-6 uppercase letters → US ETF/ADR on TASE" | `detect_market()` (`symbol_mapper.py:59-74`) has no such branch; ₪ simply defaults to TASE (same outcome) | Needs Review (describes a rule that isn't a code branch) |
| 13 | CLAUDE.md — market detection: "Numeric IBI IDs (5-8 digits) → TASE, unless in `_KNOWN_US_NUMERIC_IDS`. `$` suffix → US. Options: 8-digit IDs starting with 8 or 9" | `symbol_mapper.py:59-74` (`detect_market()` centralized), option regexes `^[89]\d{7}$` + `^ת[A-Z]\d+M\d+-\d+$` (:21-23) | Match |
| 14 | README.md — Past-Expiry LONG Detection (Options tab overrides expired LONGs to CLOSED) | `options_view.py:26-38` filters/relabels past-expiry LONGs via `parse_option_expiry()` (currently uncommitted change) | Match |
| 15 | CLAUDE.md — agorot: ingestion ÷100, yfinance `.TA` returns ILA ÷100 | `base_classifier.py:21-29` (÷100 for ₪); `price_fetcher.py:177-198` `_normalize_tase()` — yfinance always ÷100, Twelvedata heuristic: price > 10,000 → agorot | Match (Twelvedata heuristic threshold undocumented) |
| 16 | All docs — 12 SQLite tables, WAL mode, transactions 26 columns | `db.py`: exactly 12 CREATE TABLE, `PRAGMA journal_mode=WAL` (:11), 26 columns (:21-48), 2 migration blocks | Match |
| 17 | All docs — 21 IBI transaction types | `ibi_classifier.py:59-184` handles all 21 Hebrew types incl. forex_buy/forex_sell on 99028, הטבה price=0→split / price>0→bonus | Match |
| 18 | All docs — phantom rules (999*, 99028, 5039813, name keywords) | `ibi_classifier.py:6-28` | Match |
| 19 | All docs — option expiry reordering tiers `_10`/`_11`/`_12`, orphan expiry skip | `builder.py:24-41` (tiers), `builder.py:257-265` (orphan skip) | Match |
| 20 | All docs — fast-load cache (`portfolio_current`, `is_portfolio_stale()`) | `repository.py:369-437`, `builder.py:454` | Match |
| 21 | All docs — pipeline: Excel → classify → FX → dedup insert → build → prices | `ingestion.py:18-93` | Match |
| 22 | README — sidebar: API status, uploader, last import, force re-parse, refresh prices, DB info | `app.py:89-159` — all 6 present | Match |

### Constants & Weights Verification

| Constant | Documented Value | Code Value | File:Line | Status |
|----------|-----------------|------------|-----------|--------|
| CAGR days/year | 365.25 | 365.25 | performance_metrics.py:29 | Match |
| Sharpe annualization | √252 | `np.sqrt(252)` | performance_metrics.py:64 | Match |
| Min Sharpe data points | 30 | 30 | performance_metrics.py:49 | Match |
| Risk-free fallback | 4% | `_FALLBACK_RISK_FREE = 0.04` | benchmark_fetcher.py:14 | Match |
| Risk-free source | ^IRX, cached daily in metadata | ^IRX; keys `risk_free_rate`/`risk_free_rate_date` | benchmark_fetcher.py:17-48 | Match |
| Benchmarks | ^GSPC, ^TA125.TA | identical | benchmark_fetcher.py:9-12 | Match |
| Stabilization threshold | 10% | 0.10 | performance_view.py:30 | Match |
| Rolling Sharpe window | 60 days | 60 (default) | charts.py (rolling_sharpe_chart) | Match |
| `_EPS` | 0.001 | 0.001 | builder.py:21 | Match |
| Pie hole / height | 35% / 380px | 0.35 / 380 | charts.py:85 | Match |
| Treemap / waterfall / area / drawdown / monthly / sharpe heights | 450 / 400 / 420 / 250 / 350 / 300 | identical | charts.py:171, 212, 239, 261, 289, 330 | Match |
| `pnl_bar` height | "auto" | `max(300, len(syms)*30+80)` | charts.py:119 | Needs Review |
| Theme colors (7) | #10B981 #EF4444 #6366F1 #F59E0B #EC4899 #FAFBFE #1E293B | all identical; `ibi_dark` template registered | theme.py | Match |
| `_KNOWN_TASE_MAP` | 15 (README) | **16** (added 1184381 MPP "More Provident Funds") | symbol_mapper.py:26-43 | **Mismatch** |
| `_KNOWN_US_NUMERIC_IDS` | exists (CLAUDE.md) | 2 entries (GOGL, SMED) | symbol_mapper.py:48-51 | Match |
| `_HEBREW_ABBREVS` | exists (README) | 8 entries | symbol_mapper.py:168-177 | Match |
| Twelvedata agorot heuristic | — (undocumented) | price > 10,000 → ÷100 | price_fetcher.py:192 | Undocumented |

### Undocumented Code

| # | Item | Location | Notes |
|---|------|----------|-------|
| 1 | Presentation generator | `scripts/generate_presentation.py` | Playwright screenshots of all 7 tabs → stitched PNGs → PowerPoint. Untracked, referenced by nothing in src/tests. |
| 2 | Presentation output | `output/Portfolio_Dashboard_Presentation.pptx`, `output/screenshots/` (7 PNGs) | Generated artifacts; should be gitignored, not docs material. |
| 3 | One-off analysis JSONs | `db_analysis.json`, `msft_excel_analysis.json`, `tx_type_analysis.json` (repo root) | MSFT/IBM/TSLA transaction-type exploration artifacts. Referenced by nothing. |
| 4 | Verification spreadsheets | `tests/verification_data/` (2 Hebrew .xlsx: פורטפוליו 2026-04-02, תשואה Q1 2026) | Not loaded by any test — manual cross-check data. Purpose undocumented. |
| 5 | `tase_symbol_map.updated_at` | db.py:153, repository.py:362 | Extra timestamp column absent from MASTER_PLAN schema. |
| 6 | `_UNRESOLVABLE` sentinel | symbol_mapper.py:119-122 | Runtime-cache negative result to avoid repeated API calls; not described in docs. |
| 7 | `get_cash_flow_transactions()`, `get_all_fx_rates()` | repository.py:442, :460 | Cash Flow tab data accessors, not in any doc (acceptable — internal CRUD). |

### Dead References / Dead Code

| # | Item | Status |
|---|------|--------|
| 1 | `waterfall_pnl()` (`charts.py:175-216`) | **Dead code** — defined, documented in README/USER_GUIDE chart tables, never called by any view. |
| 2 | "Portfolio has no positive values to display." (flagged 2026-03-08 → 2026-04-07) | **Resolved** — string no longer present in `performance-tab-why-how-what.md` or src/. |
| 3 | `.env.template` (referenced by the re-evaluation skill itself) | Does not exist; actual file is `.env.example`. |

### Configuration Alignment

| Variable | .env.example | config.py | Code Usage | Status |
|----------|--------------|-----------|------------|--------|
| `TWELVEDATA_API_KEY` | `your_key_here` | `os.getenv("TWELVEDATA_API_KEY", "")` (config.py:15) | price_fetcher, fx_fetcher, symbol_mapper | Match |
| `YFINANCE_ENABLED` | `true` | `os.getenv("YFINANCE_ENABLED", "true").lower() == "true"` (config.py:16) | price_fetcher, fx_fetcher | Match |

No env vars used in code are missing from `.env.example`, and vice versa. `config.py` constants (BASE_DIR, EXCEL_PATH, DB_PATH) match docs. Note: `config/initial_positions.json` is a new configuration input documented in CLAUDE.md only — absent from README's Configuration section and MASTER_PLAN.

### Test Coverage

**Actual: 116 tests across 6 files** (`pytest --collect-only`)

| Test File | Tests | Covers |
|-----------|-------|--------|
| test_builder.py | 12 | Buy/sell/split/deposit flows, option short-sell cycles, cash, realized P&L |
| test_classifier.py | 34 (+5 since 04-07) | 21 types, phantoms, forex 99028, agorot normalization |
| test_performance_metrics.py | 20 | CAGR, Sharpe, max drawdown, cumulative returns |
| test_repository.py | 24 | CRUD across all tables |
| test_symbol_mapper.py | 14 | `is_option()` regexes, `parse_option_expiry()` |
| test_tase_api.py | 12 (**new**) | TASE website API lookup, name/symbol resolution, yfinance ticker conversion |

#### Test Coverage Gaps (unchanged pattern: engine tested, I/O + UI not)

| Module/Feature | Has Tests | Notes |
|----------------|-----------|-------|
| ibi_classifier / builder / repository / performance_metrics / symbol_mapper / tase_api / position | Yes | Core engine well covered |
| `src/input/excel_reader.py` | **No** | Header mapping, date sort, SHA256 hashing untested |
| `src/portfolio/ingestion.py` | **No** | End-to-end pipeline untested |
| `src/market/price_fetcher.py` | **No** | Agorot >10,000 heuristic untested — highest-risk untested logic |
| `src/market/fx_fetcher.py` | **No** | |
| `src/market/benchmark_fetcher.py` | **No** | Cache-range logic, risk-free caching untested |
| Dashboard views (6) + components (charts, position_table, styles, theme) | **No** | Typical for Streamlit UI layer |
| `src/models/transaction.py`, `src/config.py`, `db.py` | Indirect/No | Exercised via repository tests |

**Coverage: 7/34 modules (~21%), 116 tests total.**

---

## Comparison with 2026-04-07 Report

| Finding (04-07) | Status Now |
|------------------|-----------|
| README "6 tabs" / missing Cash Flow | **Fixed** — README now documents 7 tabs incl. Cash Flow, but the *order* is stale again (Cash Flow moved to Tab 3) |
| CLAUDE.md listed only 8/12 tables | **Fixed** — all 12 listed |
| `_KNOWN_TASE_MAP` 14 vs 15 | **Stale again** — now 16 entries; README still says 15 |
| USER_GUIDE 88-vs-104 test inconsistency | Partially fixed — now consistently says 104, but actual is **116** |
| `twelvedata` package missing from README tech stack | **Fixed** |
| Dead string "no positive values" | **Resolved** |
| MASTER_PLAN tab numbers / wireframes | **Still unfixed** — heading ":520 6 Tabs", wireframes :528/:600 show old 6-tab strip; worse now that Cash Flow is Tab 3 |

## Recommendations

### Priority 1 — Tab order drift (affects 4 docs)
1. README.md Dashboard Tabs table + Data Flow: renumber — Cash Flow = Tab 3, TASE = 4, US = 5, Merged = 6, Options = 7.
2. CLAUDE.md Architecture line: reorder tab list to (Statistics, Performance, Cash Flow, TASE ₪, US $, Merged ₪, Options).
3. USER_GUIDE.md :37 and :86-90: same renumbering; add cashflow_view as Tab 3.
4. MASTER_PLAN.md: fix ":520 6 Tabs" heading, update both wireframe tab strips, renumber the per-tab layout sections.

### Priority 2 — Symbol resolution chain in README
5. README.md:196: update to "runtime cache → DB cache → static map (16 known stocks) → TASE website API (no key) → Twelvedata search → None"; consider dropping the exact map count (it drifts every time a stock is added).
6. MASTER_PLAN.md Symbol Mapper section: add `tase_api.py` to the chain.

### Priority 3 — Test counts (3 docs)
7. Replace "104 tests / 5 files" with "116 tests / 6 files" in README.md:315, MASTER_PLAN.md:102, USER_GUIDE.md:42 — and add `test_tase_api.py` to both structure listings.

### Priority 4 — Project structure listings
8. Add `src/market/tase_api.py`, `tests/test_tase_api.py`, and `config/initial_positions.json` to README.md and MASTER_PLAN.md structure trees; add an Initial Positions note to README's Configuration section.

### Priority 5 — Repo hygiene (untracked artifacts)
9. Decide fate of `scripts/generate_presentation.py` (keep → document + commit; one-off → delete). Gitignore `output/`. Delete or relocate `db_analysis.json`, `msft_excel_analysis.json`, `tx_type_analysis.json`. Document what `tests/verification_data/` is for (or remove if the verification is done).

### Priority 6 — Dead code
10. Remove `waterfall_pnl()` from charts.py (and its rows in README/USER_GUIDE chart tables), or wire it into a view. Same decision pattern as the previously removed `monthly_returns_heatmap`.

### Priority 7 — Small accuracy fixes
11. README chart table: `pnl_bar` height "auto" → "dynamic (≥300px, scales with positions)".
12. Document the Twelvedata agorot heuristic (price > 10,000 → ÷100, price_fetcher.py:192) in CLAUDE.md's Agorot section — it's a real-money correctness heuristic.
13. MASTER_PLAN `tase_symbol_map` schema: add `updated_at`.
14. README "14 symbols are affected" (pre-transfer phantoms): re-verify the count now that initial positions seed 4 US symbols.

### Priority 8 — Test coverage (optional)
15. Highest value: `price_fetcher._normalize_tase()` (the >10,000 heuristic), `excel_reader.py` (hashing/date parsing), `ingestion.py` end-to-end with a small fixture Excel.
