# "Insufficient Shares" Investigation Report
**Date:** 2026-02-20
**Scope:** All 2065 transactions in IBI Portfolio Dashboard

---

## Executive Summary

**39 total "Insufficient shares" events** across **28 distinct symbols**, caused by 3 root causes. The stock split formula is correct. The primary issue (64%) is that the builder doesn't model option short selling.

---

## Findings

### Total Events by Category

| Category | Symbols | Events | % of Total |
|----------|---------|--------|------------|
| Options short selling (84/85 prefix) | 13 | 17 | 44% |
| Options missed by reorder (86 prefix) | 2 | 8 | 20% |
| Pre-transfer missing shares (stocks/ETFs) | 13 | 14 | 36% |
| **Total** | **28** | **39** | **100%** |

Additionally, 2 same-date ordering issues were found (SMED on 2022-05-20, VISA on 2025-06-11).

---

## Root Cause A: Options Short Selling (25 events) — HIGH PRIORITY

Many TASE options (prefix 84xxx, 85xxx, 86xxx) show sells happening chronologically BEFORE any buys. This is **legitimate short selling** — the trader writes (sells) an option contract they don't own, then later buys it back to close.

The `_reorder_options_expiry` function only fixes one specific sub-pattern: it moves `הפקדה פקיעה` (expiry credit) before the sell. It does NOT handle the general case where option sells come before option buys.

### Examples

| Symbol | Sell Date | Buy Date | Pattern |
|--------|-----------|----------|---------|
| 84011139 | 2022-06-02 (2 sells) | 2022-08-11 | Short sell, close 2 months later |
| 84047356 | 2022-06-27 | 2022-07-24 | Short sell, close 1 month later |
| 84047588 | 2022-08-11 | 2022-08-22 | Short sell, close 11 days later |
| 85030666 | 2024-06-03 (3 sells) | 2024-07-08 | Short sell, close 1 month later |
| 86158714 | 2025-12-14 | 2025-12-28 | Short sell, close 2 weeks later |
| 86202934 | 2025-12-25 (7 sells) | Never | Fully short, never closed in data |

### Sub-issue: `86` prefix — FIXED

The reorder function was updated to check the first digit only (`sym[:1] in ("8", "9")`), matching the `_OPTION_RE` pattern (`^[89]\d{7}$`). All 8-digit option symbols starting with 8 or 9 are now covered, including `86`-prefix options like `86158714` and `86202934`.

---

## Root Cause B: Pre-Transfer Missing Shares (14 events) — LOW PRIORITY

Stocks like BND, AEP, WMT, MMM, XLK, MPLX, KD, BABA, TCEHY, QYLD, 1080753, ADBE, and 1145184 were transferred INTO IBI mid-life. Initial deposits (`הפקדה`) on 2022-05-01/2022-05-06 do NOT capture the full historical position. When later sells happen, they sell MORE than what was deposited.

### Examples

| Symbol | Name | Deposited | Total Available | Sold | Shortfall |
|--------|------|-----------|-----------------|------|-----------|
| BND | Vanguard Total Bond | 40 | 40 | 42 | 2 |
| BABA | Alibaba | 11 dep + 4 buy = 15 | 15 | 26 | 11 |
| AEP | American Electric Power | Deposited X | X | X + shortfall | Small |

These are shares bought BEFORE the data starts (pre-transfer to IBI). The builder correctly has no way to know about them.

---

## Root Cause C: Same-Date Ordering (2 events) — LOW PRIORITY

On the same date and for the same symbol, a sell appears before a buy in the transaction order:

| Date | Symbol | Name | Issue |
|------|--------|------|-------|
| 2022-05-20 | SMED | SHARPS CO | Sell 76 before Buy 150 |
| 2025-06-11 | V | VISA INC | Sell 6 before Buy 3 |

---

## Stock Split Formula: CORRECT

The builder formula at `builder.py:149`:
```python
ratio = (pos.quantity + qty_abs) / pos.quantity
pos.quantity = pos.quantity * ratio
```

Simplifies to: `pos.quantity = pos.quantity + qty_abs`

This is **correct** because IBI records splits as the number of NEW shares added.

### Verification Against Real Data

| Stock | Split | Held | IBI qty_abs (new shares) | Builder Result | Expected | Status |
|-------|-------|------|--------------------------|----------------|----------|--------|
| GOOG | 20:1 | 1 | 19 | 1+19=20 | 20 | Correct |
| NVDA | 10:1 | 5 | 45 | 5+45=50 | 50 | Correct |
| SCHG | 4:1 | 66 | 198 | 66+198=264 | 264 | Correct |
| TPL | 3:1 | 2 | 4 | 2+4=6 | 6 | Correct |

> **Note:** The MASTER_PLAN formula (`ratio = qty_abs / pos.quantity`, `pos.quantity *= ratio`) would be WRONG for this data — it would set GOOG to `19*1=19` instead of 20. The MASTER_PLAN pseudocode has been updated.

---

## Transaction Classification: CORRECT

All 21 transaction types are classified correctly:

| Effect | Direction | Count |
|--------|-----------|-------|
| buy | add | 357 |
| sell | remove | 232 |
| deposit | add | 85 |
| option_expiry | add | 54 |
| stock_split | add | 7 |
| option_expiry | remove | 2 |

No misclassification issues found.

---

## Recommended Fixes

### Fix 1: Allow Negative Positions for Options (HIGH PRIORITY)

**Impact:** Eliminates 25 of 39 warnings (64%)

In `src/portfolio/builder.py`, modify the `direction == "remove"` block to allow short positions for options:

```python
elif direction == "remove":
    from src.market.symbol_mapper import is_option
    if pos.quantity < qty_abs - _EPS:
        if is_option(sym, name):
            # Options can be sold short (written) — allow negative position
            logger.debug(
                "Option short sell %s: have %.4f, selling %.4f on %s",
                sym, pos.quantity, qty_abs, date
            )
        else:
            logger.warning(
                "Insufficient shares for %s: have %.4f, need %.4f on %s",
                sym, pos.quantity, qty_abs, date
            )
            qty_abs = pos.quantity  # clamp
```

Also need to handle negative positions downstream (don't delete position when quantity < 0 for options).

### Fix 2: Widen Option Prefix in `_reorder_options_expiry` (MEDIUM PRIORITY)

**Impact:** Covers `86+` option prefixes

In `src/portfolio/builder.py` line 36, change:
```python
# From:
len(sym) == 8 and sym[:2] in ("83", "84", "85")
# To:
len(sym) == 8 and sym[:1] in ("8", "9")
```

This matches the `_OPTION_RE` pattern (`^[89]\d{7}$`) used elsewhere.

### Fix 3: Reorder Same-Date Buys Before Sells (LOW PRIORITY)

**Impact:** Fixes 2 cases

Add a secondary sort within the same date to process `add` transactions before `remove`:

```python
def sort_key(tx):
    # ... existing logic ...
    direction_priority = "0" if tx.get("share_direction") == "add" else "1"
    return tx["date"] + "_" + direction_priority
```

### Fix 4: Handle Pre-Transfer Positions (LOW PRIORITY)

**Impact:** Fixes 14 cases

**Option A (simple):** Suppress warnings for positions that were initially deposited (not bought) where the shortfall is small.

**Option B (better):** Auto-generate phantom initial deposits for the missing quantity when a sell exceeds available shares for a non-option, non-short-sale scenario.

---

## Summary

| Fix | Events Fixed | Priority | Complexity |
|-----|-------------|----------|------------|
| Allow negative option positions | 25 | HIGH | Medium |
| Widen option prefix to `[89]` | 2 (of 25) | MEDIUM | Trivial |
| Same-date buy-before-sell ordering | 2 | LOW | Low |
| Pre-transfer phantom deposits | 14 | LOW | Medium |
| **Total fixable** | **39** | | |

### Key Files
- `src/portfolio/builder.py` — Main build loop (lines 146-199)
- `src/classifiers/ibi_classifier.py` — Transaction classification (line 133+)
- `src/market/symbol_mapper.py` — Option regex (line 19)
