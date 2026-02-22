# Portfolio Dashboard — Implementation Plan (v3)

## Context

Build a fresh, modular **Streamlit** portfolio dashboard that reconstructs current stock holdings
by processing all IBI broker transactions from `Trans_Input/Transactions_IBI.xlsx` (2065 rows,
May 2022 – Dec 2025). Complete rewrite — no code copied from the Transaction project.

**Key drivers:**
- Tab 1: TASE (₪) — full-width NIS positions
- Tab 2: US ($) — full-width USD positions
- Tab 3: Merged portfolio (all in ₪ using historically-correct FX rates)
- Tab 4: Options — open options positions (NIS + USD)
- Tab 5: Performance — historical returns with benchmark comparison (S&P 500, TA-125)
- All 21 IBI transaction types handled correctly, including stock splits
- SQLite for persistence; only re-parse when Excel file changes
- **Twelvedata** (paid account) as primary; yfinance as fallback
- User can upload new Excel files → deduplicated merge into DB
- Cash balances (NIS + USD) displayed alongside positions
- Full historical portfolio state per transaction date (not just per import)
- Realized P&L tracked separately for every sell

---

## TASE Agorot Convention (Critical)

**TASE stock prices are quoted in agorot (1/100 of a shekel).** This is a fundamental property of the Tel Aviv Stock Exchange and affects every layer of the app:

| Layer | Data Source | Unit | Conversion Needed |
|---|---|---|---|
| IBI Excel `execution_price` | Raw from broker | **Agorot** | ÷ 100 → shekels during ingestion |
| Twelvedata `GET /price?exchange=TASE` | API response | **Verify at impl** | ÷ 100 if agorot; none if shekels |
| yfinance `Ticker("445015.TA")` | API response | **Verify at impl** | ÷ 100 if agorot; none if shekels |
| Dashboard display | All tabs | **Must be shekels** | Always show ₪, never agorot |
| `price_cache` table | Stored prices | **Always shekels** | Convert before storing |
| Portfolio builder | Position avg_cost | **Always shekels** | Normalized at ingestion |

**Implementation rule:** All stored and displayed TASE prices must be in **shekels**. The ÷100 conversion is applied at the boundary (ingestion for IBI data, price_fetcher for API data), never downstream. USD stock prices are always in dollars — no conversion needed.

**Verification step (Task 11):** When implementing `price_fetcher.py`, fetch a known TASE stock (e.g. 445015/Matrix) and compare the returned value to the known market price. If the API returns ~17000 for a stock trading at ~170₪, it's agorot → apply ÷100. Log the result and set a `TASE_PRICE_IN_AGOROT` config flag.

---

## Architecture Overview

```
Trans_Input/Transactions_IBI.xlsx
        │
        ▼
src/input/excel_reader.py          ← Sort by date ASC, generate row_hash
        │
        ▼
src/classifiers/ibi_classifier.py  ← 21 types → effect, direction,
                                      cash_flow_nis, cash_flow_usd
        │
        ▼
src/database/db.py                 ← SQLite: 11 tables
src/database/repository.py        ← CRUD + dedup insert
        │
        ▼
src/portfolio/builder.py           ← Sequential pass:
                                      → nis_positions, usd_positions
                                      → nis_cash, usd_cash
                                      → daily_portfolio_state (per date)
                                      → realized_trades (per sell)
        │
        ▼
src/market/price_fetcher.py        ← Twelvedata / yfinance
src/market/fx_fetcher.py           ← Twelvedata historical USD/ILS
        │
        ▼
app.py → Streamlit
    Tab 1: TASE (₪) — full-width NIS positions
    Tab 2: US ($) — full-width USD positions
    Tab 3: Merged (₪) — all positions converted to shekels
    Tab 4: Options — open options positions
    Tab 5: Performance — historical returns vs benchmarks

src/market/benchmark_fetcher.py  ← yfinance S&P 500 / TA-125 with SQLite cache
```

---

## Project File Structure

```
Portfolio_Dashboard/
├── app.py                              # Streamlit entry point (5 tabs)
├── MASTER_PLAN.md                      # This file — architecture & implementation plan
├── README.md                           # Project overview
├── requirements.txt
├── .env.example                        # API key template
├── .gitignore
├── docs/                               # Project documentation
│   ├── performance-tab-why-how-what.md # Performance tab deep-dive
│   ├── Insufficient_Shares_Investigation_2026-02-20.md
│   ├── Project_ReEvaluation_2026-02-20.md
│   └── 2000_api_guide_eng.pdf          # IBI API reference
├── Trans_Input/
│   └── Transactions_IBI.xlsx           # Source (read-only)
├── data/
│   └── portfolio.db                    # SQLite (auto-created)
└── src/
    ├── config.py                       # .env loader + constants
    ├── database/
    │   ├── db.py                       # Schema creation, connection
    │   └── repository.py              # All DB reads/writes
    ├── input/
    │   └── excel_reader.py            # openpyxl → sorted DataFrame + row_hash
    ├── models/
    │   ├── transaction.py             # Transaction dataclass
    │   └── position.py                # Position dataclass
    ├── classifiers/
    │   ├── base_classifier.py         # BaseClassifier ABC (broker-agnostic interface)
    │   └── ibi_classifier.py          # IBIClassifier (all 21 IBI types)
    ├── portfolio/
    │   └── builder.py                 # PortfolioBuilder
    ├── market/
    │   ├── price_fetcher.py           # Twelvedata + yfinance fallback
    │   ├── fx_fetcher.py              # USD/ILS historical + current rates
    │   ├── benchmark_fetcher.py       # S&P 500 & TA-125 via yfinance + SQLite cache
    │   └── symbol_mapper.py           # Market detection, TASE symbol handling
    └── dashboard/
        ├── views/
        │   ├── portfolio_view.py      # render(positions, prices, currency_symbol, cash, title)
        │   │                          #   Renders ONE market at full width (called per tab)
        │   ├── merged_view.py         # render(portfolio, prices, price_date) — all in ₪
        │   ├── options_view.py        # render(options_nis, options_usd) — open options
        │   └── performance_view.py    # render() — historical returns + benchmark comparison
        └── components/
            ├── position_table.py      # Reusable styled position table
            ├── performance_metrics.py # CAGR, Sharpe, max drawdown, cumulative returns
            └── charts.py             # Plotly pie + bar charts
                                       # TASE chart labels use _display_label() to resolve
                                       # IBI numeric IDs (e.g. "445015") to ticker symbols
                                       # (e.g. "MTRX") via repository.get_tase_symbol()
```

---

## SQLite Schema (11 tables)

```sql
-- All parsed & classified transactions
CREATE TABLE transactions (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    date                       TEXT NOT NULL,      -- YYYY-MM-DD
    transaction_type           TEXT NOT NULL,      -- Hebrew original
    effect                     TEXT NOT NULL,      -- see Effect Taxonomy below
    is_phantom                 INTEGER NOT NULL DEFAULT 0,
    security_name              TEXT,
    security_symbol            TEXT,               -- TASE numeric ID or US ticker
    market                     TEXT,               -- 'TASE' or 'US'
    currency                   TEXT,               -- '₪' or '$'
    quantity                   REAL,               -- as-is from IBI (positive for sells too!)
    share_direction            TEXT,               -- 'add' | 'remove' | 'none'
    share_quantity_abs         REAL,               -- absolute shares to add/remove
    execution_price_raw        REAL,               -- IBI raw (agorot for NIS!)
    execution_price            REAL,               -- normalized (÷100 for NIS)
    commission                 REAL,
    additional_fees            REAL,
    amount_foreign_currency    REAL,               -- USD value (negative for purchases)
    amount_local_currency      REAL,               -- NIS value
    balance                    REAL,               -- running NIS cash (יתרה שקלית)
    capital_gains_tax_estimate REAL,
    cost_basis                 REAL,               -- in native currency (₪ or $)
    -- Pre-computed cash flow deltas (for balance reconstruction)
    cash_flow_nis              REAL,               -- signed NIS cash delta this transaction
    cash_flow_usd              REAL,               -- signed USD cash delta this transaction
    -- For merged view: cost basis expressed in NIS using date's FX rate
    fx_rate_on_date            REAL,               -- USD/ILS rate on transaction date
    cost_basis_nis             REAL,               -- cost_basis * fx_rate_on_date (for USD txns)
    row_hash                   TEXT UNIQUE         -- SHA256 dedup key
);

-- USD/ILS rate for every transaction date (and current)
CREATE TABLE fx_rates (
    date        TEXT PRIMARY KEY,    -- YYYY-MM-DD
    usd_ils     REAL NOT NULL,       -- 1 USD = X ILS
    source      TEXT                 -- 'twelvedata' | 'yfinance' | 'manual'
);

-- Historical price cache per symbol per date
CREATE TABLE price_cache (
    symbol      TEXT NOT NULL,
    market      TEXT NOT NULL,       -- 'US' or 'TASE'
    price_date  TEXT NOT NULL,       -- YYYY-MM-DD (reference date)
    price       REAL NOT NULL,
    currency    TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,       -- ISO datetime
    source      TEXT,
    PRIMARY KEY (symbol, market, price_date)
);

-- App state (file mtime, last parse, last refresh, etc.)
CREATE TABLE metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Portfolio state snapshot after every import or manual refresh
-- (current market values — requires price API)
CREATE TABLE portfolio_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date     TEXT NOT NULL,    -- YYYY-MM-DD
    created_at        TEXT NOT NULL,    -- ISO datetime
    trigger           TEXT NOT NULL,    -- 'import' | 'refresh' | 'startup'
    nis_stocks_value  REAL,             -- market value of NIS positions (₪)
    nis_cash          REAL,
    nis_total         REAL,
    usd_stocks_value  REAL,             -- market value of USD positions ($)
    usd_cash          REAL,
    usd_total         REAL,
    fx_rate           REAL,             -- current USD/ILS
    total_nis         REAL,             -- nis_total + usd_total * fx_rate
    realized_pnl_nis  REAL,             -- cumulative realized P&L in ₪ to date
    realized_pnl_usd  REAL              -- cumulative realized P&L in $ to date
);

-- Per-position detail for each portfolio snapshot
CREATE TABLE position_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id       INTEGER NOT NULL REFERENCES portfolio_snapshots(id),
    security_symbol   TEXT NOT NULL,
    security_name     TEXT,
    market            TEXT,
    currency          TEXT,
    quantity          REAL,
    average_cost      REAL,             -- in native currency
    total_invested    REAL,             -- in native currency
    total_invested_nis REAL,            -- cost basis in ₪ using historical FX rates
    market_price      REAL,
    market_value      REAL,
    unrealized_pnl    REAL,
    unrealized_pnl_pct REAL
);

-- Portfolio cost-basis state per transaction date (no price API needed)
-- Computed during builder pass; gives full historical time-series
CREATE TABLE daily_portfolio_state (
    date              TEXT PRIMARY KEY,
    -- NIS account
    nis_invested      REAL,            -- total cost basis of open NIS positions (₪)
    nis_cash          REAL,            -- NIS cash balance
    nis_total_cost    REAL,            -- nis_invested + nis_cash
    -- USD account
    usd_invested      REAL,            -- total cost basis of open USD positions ($)
    usd_cash          REAL,            -- USD cash balance
    usd_total_cost    REAL,            -- usd_invested + usd_cash ($)
    -- Merged (in NIS, using that date's FX rate)
    fx_rate           REAL,
    total_cost_nis    REAL,            -- nis_total_cost + usd_total_cost * fx_rate
    -- Cumulative realized P&L up to this date
    cum_realized_pnl_nis REAL,
    cum_realized_pnl_usd REAL
);

-- Every sell transaction recorded with realized gain/loss
CREATE TABLE realized_trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,
    security_symbol   TEXT NOT NULL,
    security_name     TEXT,
    market            TEXT,
    currency          TEXT,
    quantity_sold     REAL,
    avg_cost          REAL,            -- average cost per share at time of sale
    sale_price        REAL,            -- execution price (normalized)
    cost_total        REAL,            -- quantity_sold * avg_cost
    proceeds          REAL,            -- quantity_sold * sale_price
    realized_pnl      REAL,            -- proceeds - cost_total
    realized_pnl_pct  REAL             -- realized_pnl / cost_total * 100
);

-- Import history log
CREATE TABLE import_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at    TEXT NOT NULL,
    source_file    TEXT NOT NULL,
    rows_total     INTEGER,
    rows_new       INTEGER,
    rows_duplicate INTEGER
);

-- TASE symbol resolution cache (IBI numeric ID → ticker)
CREATE TABLE tase_symbol_map (
    ibi_id      TEXT PRIMARY KEY,    -- IBI numeric ID (e.g. "445015")
    td_symbol   TEXT,                -- Twelvedata symbol
    yf_symbol   TEXT,                -- yfinance symbol (e.g. "445015.TA")
    name        TEXT                 -- Human-readable name (e.g. "Matrix IT")
);

-- Benchmark index price cache (S&P 500, TA-125)
CREATE TABLE benchmark_cache (
    symbol     TEXT NOT NULL,        -- yfinance ticker (^GSPC, ^TA125.TA)
    date       TEXT NOT NULL,        -- YYYY-MM-DD
    close      REAL NOT NULL,        -- closing price
    fetched_at TEXT NOT NULL,        -- ISO datetime
    PRIMARY KEY (symbol, date)
);
```

---

## Transaction Classification

### BaseClassifier (generalized interface)

`src/classifiers/base_classifier.py` defines an abstract `BaseClassifier` with:
- `classify(row: dict) -> dict` — returns effect, share_direction, cash flows, cost_basis
- `detect_phantom(row: dict) -> bool`
- `normalize_price(raw_price, currency) -> float` — handles agorot ÷100 for NIS

This allows plugging in future broker adapters (e.g., Interactive Brokers, Meitav) with zero changes to the builder or dashboard layers — only a new classifier file.

### IBI Effect Taxonomy (21 Types)

| Hebrew Type | Effect | share_direction | cash_flow_nis | cash_flow_usd | Notes |
|---|---|---|---|---|---|
| קניה שח / קניה רצף / קניה מעוף | buy | add | amount_local_currency (neg) | 0 | NIS buy |
| קניה חול מטח | buy | add | 0 | amount_foreign_currency (neg) | USD buy |
| מכירה שח / מכירה רצף / מכירה מעוף | sell | remove | abs(amount_local_currency) | 0 | NIS sell; IBI qty is POSITIVE |
| מכירה חול מטח | sell | remove | 0 | abs(amount_foreign_currency) | USD sell |
| הפקדה | deposit | add | 0 | 0 | Pre-existing or transfer-in of shares |
| הפקדה פקיעה | option_expiry | add | 0 | 0 | Options settlement credit |
| משיכה | withdrawal | remove | 0 | 0 | Transfer-out of shares |
| משיכה פקיעה | option_expiry | remove | 0 | 0 | Options expiry debit |
| הטבה | bonus_or_split | add | 0 | 0 | ⚠ Inspect 7 rows: may be split or rights |
| הפקדה דיבידנד מטח | dividend | none | 0 | +quantity (USD div received) | Cash dividend USD |
| דיבדנד | dividend | none | +amount_local_currency | 0 | Cash dividend NIS |
| ריבית מזומן בשח | interest | none | +amount_local_currency | 0 | NIS interest |
| משיכת ריבית מטח | interest_tax | none | 0 | amount_foreign_currency (neg) | Phantom |
| משיכת מס חול מטח | tax | none | 0 | amount_foreign_currency (neg) | Phantom |
| משיכת מס מטח | tax | none | 0 | amount_foreign_currency (neg) | Phantom |
| העברה מזומן בשח | transfer | none | +/- amount_local_currency | 0 | Cash in/out NIS |
| דמי טפול מזומן בשח | fee | none | amount_local_currency (neg) | 0 | NIS fee |
| B USD/ILS (symbol 99028) | forex_buy | none | amount_local_currency (neg) | +quantity | NIS→USD conversion |

> **Note on הטבה:** Before coding, inspect all 7 rows in the DB.
> If `execution_price == 0` and `security_symbol` matches an existing position → treat as **stock split** (apply ratio = quantity / current_position_qty, adjust avg_cost).
> If execution_price > 0 → treat as **bonus shares** (add shares at 0 cost).

### Phantom Detection (exclude from portfolio entirely)

- `security_symbol` starts with "999" → IBI tax accounts (9993983, 9993975, 9993971)
- `security_symbol == "99028"` → USD/ILS forex tracking (handle as forex_buy, not a stock)
- `security_symbol == "5039813"` → Options settlement clearing account
- `security_name` contains: מס לשלם / מס ששולם / מס תקבולים / הכנס תשלום מעוף

---

## Portfolio Builder Logic

### Pre-processing (before sequential pass)

1. **Sort** all transactions by date ASC (IBI exports date-DESC)
2. **Options expiry reordering:** IBI records the sell *before* the deposit for options expiry (הפקדה פקיעה). This causes an "insufficient shares" error. Fix: for options symbols (8-digit codes starting 83/84/85), move any הפקדה פקיעה deposit to one day before the earliest sell of that symbol.
3. **Filter phantoms:** mark `is_phantom=1` in DB; exclude from position building.
4. **Fetch FX rates:** for every unique date in the transaction set, ensure `fx_rates` table has a rate. Bulk-fetch missing dates from Twelvedata before the pass begins.

### Sequential Pass (chronological, per transaction)

```
positions_nis = {}   # symbol → Position
positions_usd = {}
nis_cash = 0.0
usd_cash = 0.0
cum_realized_pnl_nis = 0.0
cum_realized_pnl_usd = 0.0
current_date = None

for tx in sorted_transactions:

    # Accumulate cash flows (pre-computed in classifier)
    nis_cash += tx.cash_flow_nis
    usd_cash += tx.cash_flow_usd

    if tx.is_phantom or tx.share_direction == 'none':
        record_daily_state(tx.date) if tx.date != current_date
        continue

    positions = positions_nis if tx.currency == '₪' else positions_usd
    pos = positions.setdefault(tx.security_symbol, new_empty_position())

    if tx.share_direction == 'add':
        # BUY / DEPOSIT / BONUS
        pos.quantity += tx.share_quantity_abs
        pos.total_invested += tx.cost_basis
        pos.total_invested_nis += tx.cost_basis_nis   # ← historical FX baked in
        pos.average_cost = pos.total_invested / pos.quantity

    elif tx.share_direction == 'remove':
        # SELL / WITHDRAWAL
        assert pos.quantity >= tx.share_quantity_abs - 0.01
        realized = tx.share_quantity_abs * (tx.execution_price - pos.average_cost)
        record_realized_trade(tx, pos.average_cost, realized)
        if tx.currency == '₪':
            cum_realized_pnl_nis += realized
        else:
            cum_realized_pnl_usd += realized
        reduce_factor = tx.share_quantity_abs / pos.quantity
        pos.quantity -= tx.share_quantity_abs
        pos.total_invested *= (1 - reduce_factor)
        pos.total_invested_nis *= (1 - reduce_factor)
        if pos.quantity < 0.001:
            del positions[tx.security_symbol]  # fully closed

    elif tx.effect == 'stock_split':
        ratio = tx.share_quantity_abs / pos.quantity
        pos.quantity *= ratio
        pos.average_cost /= ratio
        # total_invested and total_invested_nis unchanged

    # Record daily state at date boundary
    if tx.date != current_date:
        record_daily_state(tx.date, positions_nis, positions_usd,
                           nis_cash, usd_cash,
                           cum_realized_pnl_nis, cum_realized_pnl_usd)
        current_date = tx.date

# Filter: return only positions with quantity > 0.001
```

### Cost Basis Rules

| Effect | cost_basis (native) | cost_basis_nis |
|---|---|---|
| NIS buy | `abs(amount_local_currency)` | same (already ₪) |
| USD buy | `abs(amount_foreign_currency)` | `cost_basis * fx_rate_on_date` |
| Deposit (הפקדה) | `quantity * execution_price` (normalized) | `× fx_rate` if USD |
| Bonus shares | `0.0` | `0.0` |
| Stock split | no cost change | no cost change |

**NIS normalization:** IBI execution prices for TASE stocks are in **agorot** → divide by 100.

---

## Market Data

### Price Fetching (`src/market/price_fetcher.py`)

Prices are fetched for a **reference date** (the latest transaction date, via `get_max_transaction_date()`), not as live quotes. This gives a consistent, reproducible valuation tied to the data.

| Market | Twelvedata call | yfinance fallback |
|---|---|---|
| US stocks | `GET /time_series?symbol=AAPL&interval=1day&start_date={date}&end_date={date}` | `yf.Ticker("AAPL").history(start=date, end=date+5days)` |
| TASE stocks | `GET /time_series?symbol=445015&interval=1day&exchange=TASE&start_date={date}&end_date={date}` | `yf.Ticker("445015.TA").history(start=date, end=date+5days)` |
| Options/warrants | Skip (non-priceable) | — |

**TASE price normalization:** TASE prices may be returned in **agorot** (see Agorot Convention section above). The fetcher must detect and convert to shekels (÷100) before storing in `price_cache`. All cached and displayed prices are in **shekels** for NIS or **dollars** for USD — never agorot.

Cache in `price_cache` table: keyed by `(symbol, market, price_date)`. Historical prices are cached permanently (no TTL) since they do not change.

### FX Rates (`src/market/fx_fetcher.py`)

- **Historical bulk fetch:** `GET /time_series?symbol=USD/ILS&interval=1day&outputsize=5000`
  → covers full date range in one call; store all in `fx_rates` table.
- **Reference date rate:** `repository.get_fx_rate(price_date)` (for merged view display — uses the rate on the reference date, not a live rate).
- On startup: fetch any dates in `transactions` not yet in `fx_rates`.

### Symbol Mapper (`src/market/symbol_mapper.py`)

Market detection (in priority order):
1. `currency == '$'` → US market
2. `currency == '₪'` AND symbol is 1–6 uppercase letters (regex `^[A-Z]{1,6}$`) → US ETF/ADR on TASE
3. Symbol is numeric (5–8 digits) → TASE
4. Symbol matches option pattern (`^[89]\d{7}$` or `^ת.*M\d{3}-\d{2}$`) → option, skip pricing
5. Default: TASE

---

## Dashboard Layout (Streamlit — 5 Tabs)

### Tab 1: TASE (₪) — full-width NIS positions

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  IBI Portfolio Dashboard        [Prices as of: YYYY-MM-DD]           [▶ sidebar]  │
├───────────┬──────────┬────────────┬────────────┬──────────────────────────────────┤
│  TASE (₪) │  US ($)  │ Merged (₪) │  Options   │  Performance                    │
├───────────┴──────────┴────────────┴────────────┴──────────────────────────────────┤
│  ┌──── TASE Account (₪) ─────────────────────────────────────────────────┐│
│  │ [Invested] [Market] [P&L] [P&L%]                                     ││
│  │ [Cash: ₪ XXX]                                                        ││
│  │ Position table (NIS positions, full width)                           ││
│  │ Pie chart                                                            ││
│  └──────────────────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────────────────┘
```

Rendered via `portfolio_view.render(positions, prices, currency_symbol, cash, title)` — called once per market tab, each at full width.

### Tab 2: US ($) — full-width USD positions

```
┌───────────────────────────────────────────────────────────────────────────┐
│  ┌──── US Account ($) ───────────────────────────────────────────────────┐│
│  │ [Invested] [Market] [P&L] [P&L%]                                     ││
│  │ [Cash: $ XXX]                                                        ││
│  │ Position table (USD positions, full width)                           ││
│  │ Pie chart                                                            ││
│  └──────────────────────────────────────────────────────────────────────┘│
└───────────────────────────────────────────────────────────────────────────┘
```

### Tab 3: Merged Portfolio (all in ₪)

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Merged Portfolio              USD/ILS: X.XXXX (historical, ref date)     │
│                                                                           │
│  [Total Invested ₪] [Market Value ₪] [Total P&L ₪] [P&L %]              │
│  [NIS Cash: ₪XXX]  [USD Cash: $XXX = ₪XXX]  [Total Cash: ₪XXX]          │
│                                                                           │
│  Combined position table (all in ₪):                                     │
│  Symbol | Name | Mkt | Qty | Cost(₪) | Price(₪) | Value(₪) | P&L | P&L% │
│    ← NIS positions: cost and value native                                 │
│    ← USD positions: cost = historical FX × USD cost;                      │
│                      value = qty × price_usd × fx_rate_on_reference_date  │
│                                                                           │
│  Pie chart: full portfolio allocation in ₪                                │
│  Bar chart: P&L per position in ₪                                        │
└───────────────────────────────────────────────────────────────────────────┘
```

**Merged view FX logic:**
- FX rate = historical rate for the reference date: `fx = repository.get_fx_rate(price_date)`
- `NIS position value (₪)` = `quantity × price_nis` (native, at reference date)
- `USD position cost (₪)` = `total_invested_nis` (weighted sum of historical FX rates, stored in DB)
- `USD position value (₪)` = `quantity × price_usd × fx_rate_on_reference_date`
- `USD cash (₪)` = `usd_cash × fx_rate_on_reference_date`

### Tab 4: Options — open options positions

```
┌───────────────────────────────────────────────────────────────────────────┐
│  Open Options Positions                                                   │
│                                                                           │
│  NIS Options table (if any):                                             │
│  Symbol | Name | Qty | Avg Cost (₪) | Invested (₪)                      │
│                                                                           │
│  USD Options table (if any):                                             │
│  Symbol | Name | Qty | Avg Cost ($) | Invested ($)                       │
│                                                                           │
│  st.info if no options positions found                                   │
└───────────────────────────────────────────────────────────────────────────┘
```

Rendered via `options_view.render(options_nis, options_usd)`. Options positions are separated from stock positions during the builder pass using `symbol_mapper.is_option()`.

### Tab 5: Performance — historical returns with benchmark comparison

```
┌───────────────────────────────────────────────────────────────────────────┐
│  [Total Return] [CAGR] [Max Drawdown] [Sharpe Ratio]  ← 4 metric cards  │
│  S&P 500: Total Return +XX.X% | CAGR +XX.X%           ← benchmark caps  │
│  TA-125:  Total Return +XX.X% | CAGR +XX.X%                             │
│  ─────────────────────────────────────────────────                       │
│  Portfolio Value Over Time (₪)                         ← Plotly chart 1  │
│  ─────────────────────────────────────────────────                       │
│  Cumulative Returns vs Benchmarks (base 100)           ← Plotly chart 2  │
│  ─ Portfolio (blue solid)                                                │
│  ─ S&P 500 (orange dashed)                                              │
│  ─ TA-125 (green dashed)                                                │
│                                                                           │
│  "Portfolio value is based on cost basis + cumulative realized P&L.      │
│   It does not reflect unrealized gains/losses on open positions."        │
└───────────────────────────────────────────────────────────────────────────┘
```

Rendered via `performance_view.render()` (no parameters). Key design decisions:

- **Historical data only** — charts display stored daily portfolio states; no forward-looking projections or live market value injection
- **Stabilization detection** — automatically skips initial account build-up period (>10% daily swings from bulk imports)
- **Benchmarks** — S&P 500 (`^GSPC`) and TA-125 (`^TA125.TA`) fetched via yfinance with permanent SQLite cache (`benchmark_cache` table)
- **Valuation method** — cost basis + realized P&L only (consistent with `daily_portfolio_state` methodology)
- **Metrics** — CAGR uses 365.25 days/year; Sharpe uses 4% risk-free rate, 252 trading days, min 30 data points

See [docs/performance-tab-why-how-what.md](docs/performance-tab-why-how-what.md) for full architectural deep-dive.

### Sidebar

- **Import new transactions:** `st.file_uploader` (`.xlsx`)
  - Upload → read & sort → classify → generate `row_hash` → dedup insert
  - Shows: "Imported X new rows, Y duplicates skipped"
  - Logs to `import_log`; triggers FX fetch for new dates; triggers snapshot
- Last import: filename / datetime / rows added
- Last price refresh: datetime
- `[Force Re-parse]` — reloads Trans_Input file from disk
- Twelvedata API status: ✓ / ✗

---

## Environment / Config

```ini
# .env
TWELVEDATA_API_KEY=your_key_here
YFINANCE_ENABLED=true           # fallback toggle
# Future broker integrations or services:
# IB_API_KEY=
# ALPHA_VANTAGE_API_KEY=
```

`src/config.py` active constants:
- `BASE_DIR` — project root directory
- `EXCEL_PATH = "Trans_Input/Transactions_IBI.xlsx"`
- `DB_PATH = "data/portfolio.db"`
- `TWELVEDATA_API_KEY` — from `.env`
- `YFINANCE_ENABLED` — fallback toggle from `.env`
- `TASE_PRICE_IN_AGOROT` — runtime flag for agorot ÷ 100 conversion

---

## New Excel Import Flow

```
User uploads new .xlsx in sidebar
    │
    ▼
excel_reader.py  →  read, sort ASC, generate row_hash per row
    │
    ▼
ibi_classifier.py  →  classify each row
    │  (pre-compute: effect, share_direction, cash_flow_nis, cash_flow_usd,
    │   cost_basis, cost_basis_nis, execution_price normalized)
    ▼
fx_fetcher.py  →  fetch FX rates for any new dates
    │
    ▼
repository.insert_transactions_deduped()
    ├── INSERT OR IGNORE (row_hash UNIQUE constraint handles dedup)
    ├── Return (rows_new, rows_duplicate)
    └── Log to import_log
    │
    ▼
portfolio/builder.py  →  full sequential pass (always from first transaction)
    ├── Writes daily_portfolio_state for every unique date
    ├── Writes realized_trades for every sell
    └── Returns current positions + cash
    │
    ▼
price_fetcher.py  →  fetch current prices for all open positions
    │
    ▼
repository.save_snapshot()  →  portfolio_snapshots + position_snapshots
```

---

## Historical Analysis

### Performance Tab (implemented — Tab 5)

Uses `daily_portfolio_state` to render:
- **Portfolio Value Over Time** — line chart of cost basis + realized P&L in ₪
- **Cumulative Returns vs Benchmarks** — base-100 normalized comparison against S&P 500 and TA-125
- **Key Metrics** — Total Return, CAGR, Max Drawdown, Sharpe Ratio
- Stabilization detection auto-skips initial build-up period

### From `daily_portfolio_state` (cost basis, no price API):
- Total capital deployed over time (line chart) ✅ (Performance tab)
- NIS cash + USD cash over time
- Net inflows vs reinvested proceeds

### From `portfolio_snapshots` (market values, at each import/refresh):
- Portfolio market value over time
- Return since inception: `(current_total_nis - first_total_nis) / first_total_nis`
- MTD / YTD comparisons (compare two snapshots)

### From `realized_trades`:
- Total realized P&L by year / by stock
- Win rate (% of trades profitable)
- Best/worst trades

### Combined:
- Total return = realized P&L + unrealized P&L (from current snapshot)
- Cash drag analysis = cash as % of total portfolio

---

## Additional Implementation Details

- **Reference date pricing:** `get_max_transaction_date()` returns the latest transaction date from the DB. All price fetches and FX rates use this as the reference date, giving a consistent valuation point tied to the data.
- **"Prices as of" header:** The dashboard header displays "Prices as of: YYYY-MM-DD" showing the reference date used for all valuations.
- **Sidebar CSS:** Custom CSS is applied to narrow the sidebar width for a cleaner layout.
- **price_cache migration:** `db.py` includes a migration block that adds the `price_date` column and updates the primary key if upgrading from the old `(symbol, market)` schema.
- **TASE chart label resolution:** `_display_label()` in charts resolves IBI numeric security IDs (e.g., "445015") to human-readable ticker symbols (e.g., "MTRX") via `repository.get_tase_symbol()`.

---

## Requirements

```
streamlit>=1.32.0
pandas>=2.1.0
openpyxl>=3.1.2
plotly>=5.18.0
requests>=2.31.0
python-dotenv>=1.0.0
yfinance>=0.2.66
```

---

## Implementation Order

1. ✅ **Scaffolding** — folders, `requirements.txt`, `.env.example`, `.gitignore`
2. ✅ **Config** — `src/config.py`
3. ✅ **Database** — `src/database/db.py` (11 tables), `src/database/repository.py`
4. ✅ **Excel reader** — `src/input/excel_reader.py` (read, sort ASC, `row_hash`)
5. ✅ **Models** — `src/models/transaction.py`, `src/models/position.py`
6. ✅ **Classifier** — `base_classifier.py` (ABC) + `ibi_classifier.py` (all 21 types + cash flows + cost_basis_nis)
7. ✅ **FX fetcher** — `src/market/fx_fetcher.py` (bulk historical fetch on startup)
8. ✅ **Ingestion pipeline** — Excel → classify → fetch FX → dedup insert
9. ✅ **Symbol mapper** — `src/market/symbol_mapper.py`
10. ✅ **Portfolio builder** — `src/portfolio/builder.py` (sequential pass, options reorder, split logic, daily_state, realized_trades)
11. ✅ **Price fetcher** — `src/market/price_fetcher.py` (Twelvedata + yfinance + TASE agorot verification)
12. ✅ **Snapshot writer** — `repository.save_snapshot()` (called after each import/refresh)
13. ✅ **Components** — `position_table.py` (with cash row), `charts.py`, `performance_metrics.py`
14. ✅ **Views** — `portfolio_view.py` (Tab 1: TASE, Tab 2: US), `merged_view.py` (Tab 3)
15. ✅ **Options tab** — `options_view.py` (Tab 4: open options positions)
16. ✅ **Performance tab** — `performance_view.py` (Tab 5: historical returns + benchmarks), `benchmark_fetcher.py`
17. ✅ **App entry point** — `app.py` (5 tabs + sidebar uploader)
18. ✅ **הטבה inspection** — query the 7 rows from DB; confirm split vs bonus; adjust classifier

---

## Verification Checklist

```bash
pip install -r requirements.txt
cp .env.example .env        # add TWELVEDATA_API_KEY
streamlit run app.py

# Structure
[x] DB created at data/portfolio.db with 11 tables
[x] Trans_Input file parsed on first run; all 2065 rows ingested

# Tab 1 — TASE (₪)
[x] Full-width NIS positions with cash card visible
[x] NIS cash ≈ last 'balance' value in original Excel (יתרה שקלית column)

# Tab 2 — US ($)
[x] Full-width USD positions with cash card visible

# Tab 3 — Merged (₪)
[x] All positions shown in ₪
[x] USD position cost uses historical FX rate (not today's rate)
[x] USD position value uses FX rate on reference date
[x] NIS cash + USD cash (converted) both displayed
[x] Historical USD/ILS rate for reference date shown

# Tab 4 — Options
[x] NIS and USD options positions displayed separately
[x] Empty state handled gracefully

# Tab 5 — Performance
[x] 4 metric cards: Total Return, CAGR, Max Drawdown, Sharpe Ratio
[x] Benchmark captions for S&P 500 and TA-125
[x] Portfolio Value Over Time chart (₪)
[x] Cumulative Returns vs Benchmarks chart (base 100)
[x] Stabilization detection skips initial build-up period
[x] Historical data only — no forward-looking projections
[x] Benchmark data cached in benchmark_cache table

# Import
[x] Upload same Excel via sidebar → "0 new rows, 2065 duplicates"
[x] Upload a new Excel with 10 extra rows → "10 new, 2065 duplicates"
[x] import_log shows both uploads

# History
[x] daily_portfolio_state has one row per unique transaction date (~750 rows)
[x] realized_trades has one row per sell transaction

# Prices
[x] TASE stock (e.g. 445015/מטריקס) price displayed in shekels (not agorot)
[x] US stock (e.g. AAPL) price displayed in dollars
```
