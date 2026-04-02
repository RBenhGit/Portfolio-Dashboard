# Options Module Re-Evaluation Report

**Date:** 2026-04-02
**Focus:** Options Module (Tab 6, builder options logic, classifier option types, symbol detection)
**Previous Report:** 2026-03-08 (full project scope — this report narrows to the options module)

## Executive Summary

The options module's core logic — detection, expiry reordering, short-sell support, orphan expiry skip, position separation, and pricing exclusion — is correct and well-designed. However, MASTER_PLAN.md has 5 stale references: wrong tab numbers for Options (says Tab 5, actually Tab 6), TASE/US, and Performance tabs, plus an outdated wireframe showing separate NIS/USD tables rather than the actual merged single table with Currency + Direction columns. One code quality issue exists: a deprecated `df.style.applymap()` call in `options_view.py:76` (deprecated since pandas 2.1.0, the project's own minimum version). A display limitation causes short option positions to always show avg cost of 0. Test coverage for options-specific logic is thin (orphan expiry and classifier tested, but `is_option()`, short-sell flow, and `_reorder_options_expiry()` lack direct tests). README.md and USER_GUIDE.md are accurate.

---

## Findings

### Documentation Accuracy

| # | Area | Doc Says | Code Does | Status |
|---|------|----------|-----------|--------|
| 1 | MASTER_PLAN.md:810 — Options tab number | "Tab 5: open options positions" | Options is Tab 6 (`app.py:181-182`) | **Mismatch** |
| 2 | MASTER_PLAN.md:809 — Portfolio view tab numbers | "portfolio_view.py (Tab 2: TASE, Tab 3: US)" | Statistics=Tab 1, Performance=Tab 2, TASE=Tab 3, US=Tab 4 (`app.py:181-182`) | **Mismatch** |
| 3 | MASTER_PLAN.md:811 — Performance tab number | "performance_view.py (Tab 6: historical returns)" | Performance is Tab 2 (`app.py:181-182`) | **Mismatch** |
| 4 | MASTER_PLAN.md:648-661 — Tab 6 wireframe | Shows two separate NIS/USD tables with columns "Symbol, Name, Qty, Avg Cost, Invested" | Code merges NIS+USD into a single table with columns "Symbol, Name, Currency, Direction, Quantity, Avg Cost, Total Invested" plus summary metrics row and two toggles | **Mismatch** |
| 5 | MASTER_PLAN.md:870 — Verification checklist | "NIS and USD options positions displayed separately" | Positions are merged into one table with a Currency column | **Mismatch** |
| 6 | USER_GUIDE.md:846-863 — Options view layout | Describes merged table with Currency+Direction, summary metrics, two toggles | Matches code exactly | Match |
| 7 | README.md:55 — Options tab row | "Open/closed options with direction badges (LONG/SHORT/CLOSED), summary metrics, toggle for open-only filter + interactive table" | Matches code exactly | Match |
| 8 | README.md:179 — Tab 6 reference | "Tab 6: Options — open options positions" | Correct tab number | Match |
| 9 | README.md:188 — Option expiry reordering description | Describes sort key mechanism correctly | Matches `builder.py:22-52` | Match |
| 10 | Option detection regex | `^[89]\d{7}$` documented in USER_GUIDE:354-358 | Matches `symbol_mapper.py:19` | Match |
| 11 | Option expiry classification | הפקדה פקיעה → `option_expiry`/`add`; משיכה פקיעה → `option_expiry`/`remove` | Matches `ibi_classifier.py` | Match |
| 12 | Options excluded from pricing | USER_GUIDE:320 "Skip if security is an option" | Matches `price_fetcher.py:33-34` | Match |

### Code Quality Issues

| # | Item | Location | Description |
|---|------|----------|-------------|
| 1 | Deprecated pandas API | `options_view.py:76` | `df.style.applymap(...)` was deprecated in pandas 2.1.0 (the project requires `pandas>=2.1.0`). Replacement: `df.style.map(...)`. Produces a `FutureWarning` at runtime when the interactive table toggle is enabled. |

### Design Analysis (Options Business Logic)

**Correct by design:**

- **Option detection** via dual regex (`_OPTION_RE` for 8-digit symbols starting with 8/9, `_OPTION_NAME_RE` for Hebrew option name pattern `^ת[A-Z]\d+M\d+-\d+$`) — used consistently across `symbol_mapper.py:19-20`, `builder.py:14`, and `price_fetcher.py:33`.
- **Expiry reordering** (`_reorder_options_expiry()` at `builder.py:22-52`) correctly fixes the IBI ordering bug where expiry credits appear after sells on the same date, by adjusting sort keys (`date_0` for adds, `date_1` for removes).
- **Orphan expiry skip** (`builder.py:166-174`) prevents phantom LONG positions when an option's original sell predates the reporting period. Condition: `effect == "option_expiry" and pos.quantity > -_EPS`.
- **Short selling** allowed for options (`builder.py:192-196`), quantity can go negative, and positions are not deleted at zero (`builder.py:237-239`).
- **Position separation** at `builder.py:247-264` — options extracted into `options_nis`/`options_usd`, keeping all (including closed with qty ≈ 0) for the UI's "open only" toggle.
- **Pricing exclusion** at `price_fetcher.py:33-34` — `is_option()` guard returns None immediately, so options have no `market_price`, `market_value`, or `unrealized_pnl`.
- **Repository serialization** at `repository.py` — options dicts are correctly included in `save_portfolio_current()` and restored via `Position.from_dict()`.

**Display limitation (not a bug):**

`Position.average_cost` returns 0 when `quantity <= 0` (`position.py:25`). For short positions created from zero, `total_invested` is zeroed by `reduce_factor=1.0` (`builder.py:232-235`), so the view's workaround (`abs(total_invested)/qty_abs` at `options_view.py:54`) also yields 0. Short options always display avg cost of 0. The premium received is correctly captured as realized P&L in the `realized_trades` table, so this is a cosmetic limitation only. A fix would require storing the short entry price separately, which is a design change beyond re-evaluation scope.

### Constants & Values Verification

| Constant | Documented Value | Code Value | File:Line | Status |
|----------|-----------------|------------|-----------|--------|
| _QTY_EPS (options view) | — | 0.001 | options_view.py:9 | N/A (undocumented local constant, matches builder _EPS) |
| _EPS (builder) | 0.001 | 0.001 | builder.py:19 | Match |
| OPT_LONG color | #10B981 (PROFIT) | theme.PROFIT | theme.py:45 | Match |
| OPT_SHORT color | #EF4444 (LOSS) | theme.LOSS | theme.py:46 | Match |
| OPT_CLOSED color | #64748B (NEUTRAL) | theme.NEUTRAL | theme.py:47 | Match |
| Direction threshold (LONG) | quantity > 0.001 | `p.quantity > _QTY_EPS` | options_view.py:33,49 | Match |
| Direction threshold (SHORT) | quantity < -0.001 | `p.quantity < -_QTY_EPS` | options_view.py:34,52 | Match |

### Test Coverage Gaps

| Module/Feature | Has Tests | Notes |
|----------------|-----------|-------|
| Orphan option expiry skip | Yes | `test_builder.py:172-199` — tests that orphan expiry credit with no prior short is skipped |
| Option expiry classification (הפקדה פקיעה, משיכה פקיעה) | Yes | `test_classifier.py:149-160` — tests both credit and debit expiry types |
| Options serialization round-trip | Indirect | `repository.py` — tested via repository CRUD tests |
| `is_option()` detection | **No** | `symbol_mapper.py:57-61` — regex matching untested directly |
| `_reorder_options_expiry()` | **No** | `builder.py:22-52` — only tested indirectly through orphan expiry test |
| Option short-sell flow | **No** | `builder.py:192-196` — negative quantity path not directly tested |
| Short-sell P&L recording | **No** | `builder.py:208-225` — realized P&L for short positions not tested |
| Direction badge logic (LONG/SHORT/CLOSED) | **No** | `options_view.py:43-63` — UI layer, typical for Streamlit apps |
| Options excluded from pricing | **No** | `price_fetcher.py:33-34` — `is_option` guard not tested |
| Statistics open options count | **No** | `statistics_view.py:90-94` — UI layer |

---

## Recommendations

### Priority 1 — Fix Documentation Drift (5 items)

1. **MASTER_PLAN.md:809** — Fix tab numbers from "Tab 2: TASE, Tab 3: US" to "Tab 3: TASE, Tab 4: US".
2. **MASTER_PLAN.md:810** — Fix Options tab number from "Tab 5" to "Tab 6".
3. **MASTER_PLAN.md:811** — Fix Performance tab number from "Tab 6" to "Tab 2".
4. **MASTER_PLAN.md:648-661** — Replace the Tab 6 wireframe. Remove the two separate NIS/USD table layout. Replace with a wireframe showing: summary metrics row (Total Positions, Long/Short, Total Capital), toggle controls (Open positions only, Interactive table), and a single merged table with columns: Symbol, Name, Currency, Direction (badge), Quantity, Avg Cost, Total Invested.
5. **MASTER_PLAN.md:870** — Change "NIS and USD options positions displayed separately" to "NIS and USD options merged into single table with Currency column".

### Priority 2 — Fix Deprecated Code (1 item)

6. **options_view.py:76** — Replace `df.style.applymap(_color_direction, subset=["Direction"])` with `df.style.map(_color_direction, subset=["Direction"])`. One-word change that eliminates a `FutureWarning` on every interactive table render.

### Priority 3 — Expand Test Coverage (optional, 3 high-value targets)

7. **`is_option()` unit tests** — Test the two regex patterns: 8-digit symbols starting with 8 or 9, and Hebrew option name pattern. Test negative cases (6-digit TASE stock IDs, US tickers, regular Hebrew names).
8. **Option short-sell integration test** — Test the full cycle: sell from zero position (creates short), expiry credit (closes position). Verify realized P&L is correct and position quantity reaches 0.
9. **`_reorder_options_expiry()` unit test** — Provide a list of transactions with expiry credits after sells, verify the output order processes credits before sells.

### Priority 4 — Known Limitation (no action required)

10. **Short position avg cost display** — Short options always show avg cost of 0. This is a known consequence of the `Position.average_cost` property returning 0 for non-positive quantities. The actual P&L is correctly tracked in `realized_trades`. A fix would require storing the short entry price separately, which is a design change beyond re-evaluation scope.
