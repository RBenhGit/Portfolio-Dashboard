# IBI Portfolio Dashboard — Complete User Guide

> A comprehensive reference covering every module, function, algorithm, and financial concept in the project.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Data Flow](#2-architecture--data-flow)
3. [Getting Started](#3-getting-started)
4. [Module Reference](#4-module-reference)
   - 4.1 [Input Layer — Excel Reader](#41-input-layer--excel-reader)
   - 4.2 [Classification Layer](#42-classification-layer)
   - 4.3 [Market Data Layer](#43-market-data-layer)
   - 4.4 [Database Layer](#44-database-layer)
   - 4.5 [Portfolio Engine](#45-portfolio-engine)
   - 4.6 [Dashboard Components](#46-dashboard-components)
   - 4.7 [Dashboard Views](#47-dashboard-views)
5. [Financial Theory Reference](#5-financial-theory-reference)
6. [Caching & Performance](#6-caching--performance)
7. [IBI Broker Quirks & Fixes](#7-ibi-broker-quirks--fixes)
8. [Test Suite](#8-test-suite)

---

## 1. Project Overview

The IBI Portfolio Dashboard is a **Streamlit-based investment portfolio tracker** that reconstructs a multi-market portfolio (Israeli TASE + US equity) from IBI broker Excel transaction exports. It processes ~2,000 Hebrew-language transactions across 21 types, handles multi-currency accounting (NIS/USD), and provides performance analytics with benchmark comparisons.

### Key Capabilities

| Feature | Description |
|---------|-------------|
| **21 Transaction Types** | Buys, sells, dividends, splits, options, deposits, withdrawals, fees, taxes |
| **Multi-Currency** | Dual tracking in native currency + NIS equivalent with historical FX rates |
| **6 Dashboard Tabs** | Statistics, Performance, TASE (₪), US ($), Merged (₪), Options |
| **8 Chart Types** | Area, drawdown, bar, treemap, waterfall, pie, rolling Sharpe, monthly returns |
| **Benchmark Comparison** | S&P 500 and TA-125 with indexed returns |
| **Performance Metrics** | CAGR, Sharpe ratio, max drawdown, cumulative returns |
| **Smart Caching** | Fast-load portfolio cache, price cache, FX cache, benchmark cache |
| **88 Unit Tests** | Builders, classifiers, metrics, and database CRUD |

### Project Structure

```
Portfolio_Dashboard/
├── app.py                           # Streamlit entry point
├── requirements.txt                 # 9 dependencies
├── .env                             # API keys (not in repo)
├── Trans_Input/
│   └── Transactions_IBI.xlsx        # IBI broker export (~2,065 rows)
├── data/
│   └── portfolio.db                 # SQLite database (auto-created)
├── tests/                           # 4 test files, 88 tests
├── docs/                            # Documentation
└── src/
    ├── config.py                    # Central configuration
    ├── models/
    │   ├── transaction.py           # Transaction dataclass
    │   └── position.py              # Position dataclass
    ├── input/
    │   └── excel_reader.py          # IBI Excel parser
    ├── classifiers/
    │   ├── base_classifier.py       # Abstract classifier
    │   └── ibi_classifier.py        # 21 IBI transaction types
    ├── market/
    │   ├── symbol_mapper.py         # TASE ID → ticker resolution
    │   ├── price_fetcher.py         # Security price fetching
    │   ├── fx_fetcher.py            # USD/ILS exchange rates
    │   └── benchmark_fetcher.py     # S&P 500 & TA-125 data
    ├── portfolio/
    │   ├── builder.py               # Sequential portfolio build engine
    │   └── ingestion.py             # Full ingestion pipeline
    ├── database/
    │   ├── db.py                    # SQLite schema (12 tables)
    │   └── repository.py            # All CRUD operations
    └── dashboard/
        ├── theme.py                 # Color palette & Plotly template
        ├── styles.py                # CSS + HTML helpers
        ├── components/
        │   ├── charts.py            # 8 Plotly chart functions
        │   ├── position_table.py    # Styled HTML position table
        │   └── performance_metrics.py  # CAGR, Sharpe, drawdown
        └── views/
            ├── statistics_view.py   # Tab 1: Summary & analytics
            ├── performance_view.py  # Tab 2: Historical performance
            ├── portfolio_view.py    # Tabs 3–4: Single-market view
            ├── merged_view.py       # Tab 5: All positions in ₪
            └── options_view.py      # Tab 6: Options positions
```

---

## 2. Architecture & Data Flow

### Pipeline Overview

```
IBI Excel (.xlsx)
    │
    ▼
┌────────────────────────────────────────┐
│  Excel Reader                          │
│  Normalize Hebrew columns, parse dates │
│  Generate SHA-256 row hash per row     │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  IBI Classifier                        │
│  Classify 21 transaction types         │
│  Detect phantoms, normalize prices     │
│  Calculate cost basis & cash flows     │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  FX Fetcher                            │
│  Fetch historical USD/ILS for all      │
│  transaction dates                     │
│  (Twelvedata → yfinance fallback)      │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  Backfill + Dedup Insert               │
│  cost_basis_nis = cost_basis × fx_rate │
│  Insert to DB (skip dupes by hash)     │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  Portfolio Builder                     │
│  Sequential pass over all transactions │
│  Track positions, cash, realized P&L   │
│  Record daily portfolio state          │
│  Fetch closing prices per date         │
└────────────┬───────────────────────────┘
             │
             ▼
┌────────────────────────────────────────┐
│  Streamlit Dashboard (6 tabs)          │
│  Load cached portfolio + prices        │
│  Render charts, tables, metrics        │
└────────────────────────────────────────┘
```

### Startup Flow (app.py)

1. **`_init()`** — Create DB schema (cached, runs once)
2. **`_initial_ingest()`** — Parse Excel if DB is empty
3. **`_get_portfolio()`** — Load portfolio from fast-load cache or rebuild
4. **`_get_prices()`** — Fetch current market prices
5. **Render 6 tabs** — Pass portfolio + prices to each view

---

## 3. Getting Started

### Prerequisites

- Python 3.10+
- Twelvedata API key (free tier works; needed for TASE symbol resolution)

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Create a `.env` file:

```
TWELVEDATA_API_KEY=your_key_here
YFINANCE_ENABLED=true
```

### Input Data

Place your IBI broker Excel export at `Trans_Input/Transactions_IBI.xlsx`.

### Run

```bash
streamlit run app.py
```

### Sidebar Controls

| Control | Action |
|---------|--------|
| **Import Transactions** | Upload a new IBI Excel file |
| **Force Re-parse** | Re-ingest the existing Excel file |
| **Refresh Prices** | Clear price cache and refetch |

---

## 4. Module Reference

### 4.1 Input Layer — Excel Reader

**File:** `src/input/excel_reader.py`

#### `read_excel(path: str | Path) -> pd.DataFrame`

Reads an IBI broker Excel (.xlsx) file and normalizes it for processing.

**Operations:**
1. Maps Hebrew column names to English via `COLUMN_MAP`
2. Converts dates from DD/MM/YYYY → YYYY-MM-DD
3. Converts numeric columns to float (fills NaN with 0)
4. Generates a SHA-256 hash per row for deduplication
5. Sorts transactions chronologically (oldest first)

**Column Mapping:**

| Hebrew | English | Description |
|--------|---------|-------------|
| תאריך | `date` | Transaction date |
| סוג פעולה | `transaction_type` | One of 21 Hebrew types |
| שם נייר | `security_name` | Security full name |
| מס' נייר / סימבול | `security_symbol` | TASE numeric ID or US ticker |
| כמות | `quantity` | Number of shares |
| שער ביצוע | `execution_price_raw` | Raw price (agorot for TASE) |
| מטבע | `currency` | ₪ or $ |
| עמלת פעולה | `commission` | Trade commission |
| עמלות נלוות | `additional_fees` | Additional fees |
| תמורה במט"ח | `amount_foreign_currency` | USD amount |
| תמורה בשקלים | `amount_local_currency` | NIS amount |
| יתרה שקלית | `balance` | Running NIS cash balance |
| אומדן מס רווחי הון | `capital_gains_tax_estimate` | Tax estimate |

**Returns:** Sorted DataFrame with all columns normalized and `row_hash` column added.

#### `iter_rows(df: pd.DataFrame)`

Generator that yields each DataFrame row as a dictionary.

---

### 4.2 Classification Layer

**Files:** `src/classifiers/base_classifier.py`, `src/classifiers/ibi_classifier.py`

#### Abstract Base: `BaseClassifier`

| Method | Description |
|--------|-------------|
| `classify(row: dict) -> dict` | Classify a transaction row (abstract) |
| `detect_phantom(row: dict) -> bool` | Detect internal/phantom transactions (abstract) |
| `normalize_price(raw_price, currency) -> float` | Convert raw price to display units |

**Price Normalization Theory:**
IBI stores TASE prices in **agorot** (1/100 of a shekel). The normalizer divides TASE prices by 100 to convert to shekels. US prices are stored in dollars and returned as-is.

#### `IBIClassifier`

Classifies all 21 IBI transaction types:

| Hebrew Type | Effect | Direction | Notes |
|-------------|--------|-----------|-------|
| קניה שח / קניה רצף / קניה מעוף | `buy` | add | NIS buy (symbol 99028 = forex) |
| קניה חול מטח | `buy` | add | USD buy |
| מכירה שח / מכירה רצף / מכירה מעוף | `sell` | remove | NIS sell |
| מכירה חול מטח | `sell` | remove | USD sell |
| הפקדה | `deposit` | add/remove | Share transfer in/out |
| הפקדה פקיעה | `option_expiry` | add | Option expiry credit |
| משיכה | `withdrawal` | remove | Share withdrawal |
| משיכה פקיעה | `option_expiry` | remove | Option expiry debit |
| הטבה | `stock_split` or `bonus` | add | Split (price=0) or bonus |
| הפקדה דיבידנד מטח | `dividend` | — | USD dividend (phantom) |
| דיבדנד | `dividend` | — | NIS dividend |
| ריבית מזומן בשח | `interest` | — | NIS interest |
| משיכת ריבית מטח | `interest_tax` | — | Foreign interest tax (phantom) |
| משיכת מס חול מטח / משיכת מס מטח | `tax` | — | Foreign taxes (phantom) |
| העברה מזומן בשח | `transfer` | — | NIS cash transfer |
| דמי טפול מזומן בשח | `fee` | — | NIS fee |

**Phantom Detection:**
Phantoms are internal IBI entries that don't represent real position changes:
- Symbols: "99028", "5039813", or starting with "999"
- Names containing: "מס לשלם", "מס ששולם", "מס תקבולים", "הכנס/תשלום מעוף"

**Market Detection (`_detect_market`):**
- Numeric symbols (5–8 digits) → TASE
- Currency "$" → US
- Currency "₪" with US ticker pattern (1–6 uppercase letters) → US (dual-listed)
- Default → TASE

---

### 4.3 Market Data Layer

**Files:** `src/market/fx_fetcher.py`, `src/market/price_fetcher.py`, `src/market/symbol_mapper.py`, `src/market/benchmark_fetcher.py`

#### 4.3.1 FX Fetcher (`fx_fetcher.py`)

##### `fetch_historical_fx(missing_dates: list[str]) -> dict[str, float]`

Fetches USD/ILS exchange rates for multiple dates.

- **Primary:** Twelvedata `/time_series` endpoint (bulk, up to 5,000 days)
- **Fallback:** yfinance `USDILS=X` pair
- **Returns:** `{date_str: rate}` for successfully fetched dates

##### `get_current_fx_rate() -> Optional[float]`

Returns the live USD/ILS rate for display. Tries Twelvedata, falls back to yfinance. Returns `None` if both fail.

#### 4.3.2 Price Fetcher (`price_fetcher.py`)

##### `get_price(security_symbol, market, security_name=None, price_date="") -> Optional[float]`

Returns the closing price on a specific date in native currency.

**Flow:**
1. Skip if security is an option (no pricing)
2. Check `price_cache` in DB
3. If cached, return immediately
4. Fetch from Twelvedata, then yfinance
5. Cache result and return

##### `fetch_prices_for_positions(positions, price_date="") -> dict[str, Optional[float]]`

Batch-fetches prices for all open positions.

##### `check_twelvedata_status() -> bool`

Validates the Twelvedata API key by calling `/api_usage`.

##### TASE Price Normalization (`_normalize_tase`)

Auto-detects whether TASE prices from APIs are in agorot or shekels:
- If price > 500 on first fetch → assumes agorot, divides by 100
- Stores detection in global to avoid re-detection

#### 4.3.3 Symbol Mapper (`symbol_mapper.py`)

##### `resolve_tase_symbol(ibi_id, security_name=None) -> dict | None`

Converts IBI numeric ID (e.g., "445015") to API tickers.

**Resolution chain (4 levels):**
1. **Runtime cache** — in-memory dict
2. **DB cache** — `tase_symbol_map` table
3. **Static known map** — ~14 hardcoded entries (e.g., "445015" → "MTRX")
4. **Twelvedata symbol_search API** — by security name

**Returns:** `{"td": "MTRX", "yf": "MTRX.TA", "name": "Matrix IT"}` or `None`

##### `is_option(security_symbol, security_name=None) -> bool`

Detects options/warrants to skip from pricing:
- Symbol matches `[89]\d{7}` (8-digit starting with 8 or 9)
- Name matches Hebrew option pattern `^ת[A-Z]\d+M\d+-\d+$`

##### `detect_market(security_symbol, currency) -> str`

Determines TASE vs US market (same logic as classifier).

#### 4.3.4 Benchmark Fetcher (`benchmark_fetcher.py`)

##### `fetch_benchmark(name, start_date, end_date) -> dict[str, float]`

Fetches benchmark daily closes with incremental caching.

**Supported Benchmarks:**

| Name | yfinance Symbol |
|------|----------------|
| S&P 500 | `^GSPC` |
| TA-125 | `^TA125.TA` |

**Caching Strategy:**
1. Check DB cache for existing date range
2. Fetch only missing ranges (before or after cached data)
3. Upsert new prices to cache
4. Filter and return requested range

##### `get_risk_free_rate() -> float`

Returns the annualized risk-free rate for Sharpe ratio calculations.

- **Source:** 13-week US Treasury bill (`^IRX`) via yfinance
- **Format:** Decimal (e.g., 0.0425 for 4.25%)
- **Caching:** Daily in metadata table
- **Fallback:** 4% if fetch fails and no cached value

---

### 4.4 Database Layer

**Files:** `src/database/db.py`, `src/database/repository.py`

#### Schema (12 Tables)

| Table | Purpose | Primary Key |
|-------|---------|-------------|
| `transactions` | Classified transaction ledger | `row_hash` (UNIQUE) |
| `fx_rates` | Historical USD/ILS rates | `date` |
| `price_cache` | Security closing prices | `(symbol, market, price_date)` |
| `metadata` | Key-value store | `key` |
| `daily_portfolio_state` | EOD portfolio snapshots | `date` |
| `realized_trades` | Per-sell realized P&L | auto-increment |
| `portfolio_snapshots` | Point-in-time summaries | auto-increment |
| `position_snapshots` | Holdings per snapshot | `(snapshot_id, symbol)` |
| `tase_symbol_map` | TASE ID → ticker cache | `ibi_id` |
| `import_log` | Import history | auto-increment |
| `benchmark_cache` | S&P 500 & TA-125 prices | `(symbol, date)` |
| `portfolio_current` | Serialized fast-load cache | `key` |

#### `get_connection() -> sqlite3.Connection`

Returns a configured SQLite connection with:
- **WAL mode** for better concurrency
- **Foreign keys** enabled
- **Row factory** = `sqlite3.Row` for dict-like access

#### Key Repository Functions

**Transactions:**

| Function | Description |
|----------|-------------|
| `insert_transactions_deduped(txns)` | Insert classified transactions, skip duplicates by `row_hash` |
| `get_all_transactions(include_phantom)` | Retrieve all transactions sorted by date |
| `get_transaction_count()` | Return total count |

**FX Rates:**

| Function | Description |
|----------|-------------|
| `upsert_fx_rates(rates, source)` | Upsert `{date: rate}` dict |
| `get_fx_rate(date)` | Get USD/ILS rate for a date |
| `get_all_fx_dates()` | Get set of dates with cached rates |

**Prices:**

| Function | Description |
|----------|-------------|
| `upsert_price(symbol, market, price, ...)` | Cache closing price |
| `get_cached_price(symbol, market, price_date)` | Retrieve cached price |

**Portfolio State:**

| Function | Description |
|----------|-------------|
| `upsert_daily_state(state)` | Record EOD portfolio state |
| `get_daily_portfolio_states()` | All daily states ordered by date |
| `save_portfolio_current(result)` | Serialize portfolio to fast-load cache |
| `load_portfolio_current()` | Deserialize from fast-load cache |
| `is_portfolio_stale()` | Check if cache is older than latest import |

**Realized Trades:**

| Function | Description |
|----------|-------------|
| `insert_realized_trade(trade)` | Record a realized gain/loss |
| `get_realized_trades()` | All trades sorted by date |

---

### 4.5 Portfolio Engine

**Files:** `src/portfolio/builder.py`, `src/portfolio/ingestion.py`, `src/models/position.py`

#### Position Dataclass (`position.py`)

Represents a single open holding:

| Field | Type | Description |
|-------|------|-------------|
| `security_symbol` | str | TASE ID or US ticker |
| `security_name` | str | Full name |
| `market` | str | "TASE" or "US" |
| `currency` | str | "₪" or "$" |
| `quantity` | float | Current share count |
| `total_invested` | float | Cumulative cost basis (native currency) |
| `total_invested_nis` | float | Cumulative cost basis (₪) |
| `market_price` | float | Latest closing price |
| `market_value` | float | quantity × market_price |
| `unrealized_pnl` | float | market_value − total_invested |
| `unrealized_pnl_pct` | float | (pnl / total_invested) × 100 |

**Properties:**
- `average_cost` → `total_invested / quantity`

**Methods:**
- `to_snapshot_dict()` — Serialize to dict for DB/cache
- `from_dict(d)` — Reconstruct from dict

#### Portfolio Builder (`builder.py`)

##### `build(trigger="startup") -> dict`

The core engine that processes all transactions and builds portfolio state.

**Algorithm:**

1. **Fetch & sort** all transactions (including phantoms for cash flows)
2. **Reorder option expiries** via `_reorder_options_expiry()` (fixes IBI ordering bug)
3. **Sequential pass** over every transaction, date by date:
   - On **date boundary**: record previous day's state (prices, market values, totals)
   - Update **NIS cash** from IBI's own balance column
   - Update **USD cash** by accumulating `cash_flow_usd`
   - Skip phantoms and non-share transactions for position tracking
   - **For ADDS** (buys, deposits, bonuses):
     - Increase quantity and total_invested
     - Special handling for stock splits (adjust ratio, keep invested unchanged)
   - **For REMOVES** (sells, withdrawals):
     - Calculate realized P&L: `qty_sold × (execution_price − average_cost)`
     - Reduce quantity and total_invested proportionally
     - Delete position if quantity ≈ 0 (except options)
4. **Record final day's state**
5. **Separate** real positions from options
6. **Cache** result to `portfolio_current` table

**Returns:**
```python
{
    "positions_nis": {symbol: Position},   # TASE stocks
    "positions_usd": {symbol: Position},   # US stocks
    "options_nis": {symbol: Position},      # TASE options
    "options_usd": {symbol: Position},      # US options
    "nis_cash": float,                      # NIS cash balance
    "usd_cash": float,                      # USD cash balance
    "cum_realized_pnl_nis": float,          # Cumulative realized P&L (NIS)
    "cum_realized_pnl_usd": float,          # Cumulative realized P&L (USD)
    "built_at": str,                        # ISO timestamp
}
```

##### `_reorder_options_expiry(transactions) -> list`

Fixes an IBI bug where option expiry credits appear *after* the sell on the same date. Adjusts sort keys so credits process first.

#### Ingestion Pipeline (`ingestion.py`)

##### `ingest(source, trigger="import") -> dict`

End-to-end pipeline:
1. Create DB schema
2. Read and normalize Excel
3. Classify each row via `IBIClassifier`
4. Fetch FX rates for all unique dates
5. Backfill `cost_basis_nis` (USD transactions × FX rate)
6. Dedup-insert to DB
7. Log import
8. Run portfolio builder
9. Return import stats + portfolio summary

---

### 4.6 Dashboard Components

#### 4.6.1 Theme (`theme.py`)

Centralized color palette and Plotly template.

**Color Constants:**

| Category | Constant | Value | Usage |
|----------|----------|-------|-------|
| Profit | `PROFIT` | `#10B981` | Green for gains |
| Loss | `LOSS` | `#EF4444` | Red for losses |
| Accent | `ACCENT_PRIMARY` | `#6366F1` | Primary indigo |
| Accent | `ACCENT_SECONDARY` | `#EC4899` | Pink accent |
| Benchmark | `BM_SP500` | `#F59E0B` | S&P 500 amber |
| Benchmark | `BM_TA125` | `#EC4899` | TA-125 pink |
| Benchmark | `BM_PORTFOLIO` | `#6366F1` | Portfolio indigo |

**Chart Colors** (12-color rotating palette):
`#6366F1`, `#EC4899`, `#F59E0B`, `#10B981`, `#06B6D4`, `#8B5CF6`, `#F97316`, `#14B8A6`, `#E879F9`, `#3B82F6`, `#84CC16`, `#FB923C`

##### `plotly_template() -> go.layout.Template`

Returns a Plotly template with transparent backgrounds, Inter font, subtle grid lines, and the project color palette.

##### `apply_theme()`

Registers the template as the Plotly default (call once at startup).

##### `pnl_color(value) -> str` / `pnl_bg_color(value) -> str`

Return green or red (solid or semi-transparent) based on P&L sign.

#### 4.6.2 Styles (`styles.py`)

CSS and HTML generation utilities.

##### `get_all_styles() -> str`

Returns the complete CSS stylesheet (`<style>` tag) with:
- Glassmorphism metric cards (gradient + blur)
- Styled table classes (`.custom-table`)
- P&L pill badges (`.pnl-pill.gain`, `.pnl-pill.loss`)
- Direction badges for options (`.direction-badge`)
- Fade-in animations

##### `metric_card_html(label, value, delta="", delta_color="") -> str`

Generates HTML for a styled metric card with optional delta arrow indicator.

##### `section_header(title) -> str`

Generates HTML for a section header with indigo accent underline.

##### `html_table(headers, rows, alignments=None) -> str`

Builds a complete styled HTML `<table>`. Callers must pre-format cell content (currency formatting, colored pills, etc.).

#### 4.6.3 Charts (`charts.py`)

Eight Plotly chart functions:

##### `allocation_pie(positions, prices, currency_symbol, title) -> Optional[go.Figure]`

**What it shows:** Donut pie chart (35% hole) of portfolio allocation by market value.

**Theory:** Asset allocation — the distribution of capital across holdings — is a core portfolio management concept. Visualizing it helps identify concentration risk.

**Calculation:** Each slice = `price × quantity` for a position. Only includes positions with positive market value.

##### `pnl_bar(positions, prices, currency_symbol, title) -> Optional[go.Figure]`

**What it shows:** Horizontal bar chart of unrealized P&L per position.

**Theory:** Unrealized P&L = `(current_price − average_cost) × quantity`. Shows which positions are contributing profits vs losses.

**Visual:** Green bars for gains, red for losses. Dynamic height based on position count.

##### `allocation_treemap(positions, prices, currency_symbol, title, fx_rate=1.0) -> Optional[go.Figure]`

**What it shows:** Hierarchical treemap where rectangle size = market value, color = P&L percentage.

**Theory:** Combines allocation (size) with performance (color) in one view. Red → losing positions, green → winning positions. Larger rectangles = larger allocations.

**Color scale:** Loss (red) → Neutral (white/gray) → Profit (green), centered at 0%.

##### `waterfall_pnl(positions, prices, currency_symbol, fx_rate=1.0) -> Optional[go.Figure]`

**What it shows:** Waterfall chart showing how individual position P&L contributions sum to total portfolio P&L.

**Theory:** Waterfall charts decompose a total into its constituent parts. Bars float and connect to show cumulative effect. Sorted largest to smallest, with a "Total" bar at the end.

##### `area_chart_with_gradient(series, name, color) -> go.Figure`

**What it shows:** Line chart with semi-transparent gradient fill underneath, used for portfolio value over time.

**Visual:** Line width 2.5px, fill opacity 8%, height 420px.

##### `drawdown_chart(series: pd.Series) -> go.Figure`

**What it shows:** "Underwater plot" — how far below the running maximum (peak) the portfolio sits at each point in time.

**Theory:** Drawdown measures peak-to-trough decline. At any time t:

```
Drawdown(t) = (Value(t) − Peak(t)) / Peak(t) × 100
```

Where `Peak(t)` is the running maximum up to time t. The value is always ≤ 0%. A drawdown of −20% means the portfolio is 20% below its all-time high at that point.

**Implementation:**
```python
cummax = series.cummax()
drawdown = (series - cummax) / cummax * 100
```

This is the **standard textbook formula**, correctly implemented. The chart fills the area between 0% and the drawdown line in semi-transparent red.

**Use case:** Investors use drawdown charts to understand worst-case scenarios — how much pain they'd experience if they bought at the peak.

##### `monthly_returns_bar(series) -> Optional[go.Figure]`

**What it shows:** Bar chart of month-over-month returns.

**Theory:** Monthly returns show performance periodicity. Calculated as:
```
Monthly Return = (End-of-Month Value / Previous End-of-Month Value − 1) × 100
```

**Requirements:** Minimum 30 data points. Green bars for positive months, red for negative.

##### `rolling_sharpe_chart(series, window=60) -> Optional[go.Figure]`

**What it shows:** Line chart of the Sharpe ratio calculated over a rolling 60-day window.

**Theory:** Shows how risk-adjusted returns evolve over time. A rising line = improving risk/reward, falling = deteriorating. Includes reference lines at 0 (breakeven) and 1.0 (good), plus the average.

**Calculation:**
```
Rolling Sharpe = (Rolling Mean of Excess Returns / Rolling Std) × √252
```

#### 4.6.4 Performance Metrics (`performance_metrics.py`)

Four financial metric functions:

##### `compute_cumulative_returns(series) -> pd.Series`

**Theory:** Normalizes a price series to base 100 for comparison across portfolios of different sizes.

**Formula:** `Cumulative Return(t) = (Price(t) / Price(0)) × 100`

**Example:** Portfolio starts at ₪50,000, grows to ₪62,500 → cumulative return = 125 (i.e., 25% gain).

##### `compute_cagr(series) -> float`

**Theory:** Compound Annual Growth Rate — the smooth annual rate needed to match actual performance. Eliminates volatility to show average yearly return.

**Formula:**
```
CAGR = (Ending Value / Starting Value) ^ (1 / Years) − 1
```
Where `Years = (end_date − start_date) / 365.25`

**Returns:** Percentage (e.g., 14.5 for 14.5%)

**Edge cases:** Returns 0.0 if < 2 data points, starting value ≤ 0, or time span ≤ 0.

##### `compute_max_drawdown(series) -> float`

**Theory:** Maximum peak-to-trough decline — the single worst drop from any peak to subsequent low. A key measure of downside risk.

**Formula:**
```
Max Drawdown = min((Value(t) − CumulativeMax(t)) / CumulativeMax(t)) × 100
```

**Returns:** Negative percentage (e.g., −25.5 for a 25.5% decline). Returns 0.0 if < 2 data points.

**Example:** Portfolio peaks at ₪100,000, drops to ₪72,000 → Max Drawdown = −28%.

##### `compute_sharpe_ratio(series, risk_free_annual=None) -> float`

**Theory:** The Sharpe ratio measures **excess return per unit of risk (volatility)**. Higher = better risk-adjusted returns.

**Formula:**
```
Daily Risk-Free = Annual Rate / 252
Excess Returns = Daily Returns − Daily Risk-Free
Sharpe = (Mean(Excess Returns) / Std(Excess Returns)) × √252
```

**Interpretation:**
| Sharpe | Meaning |
|--------|---------|
| < 0 | Underperforms risk-free rate |
| 0 – 0.5 | Below average |
| 0.5 – 1.0 | Average (historical S&P 500 ≈ 0.5–0.7) |
| 1.0 – 2.0 | Good |
| > 2.0 | Excellent |

**Risk-free rate:** Fetches 13-week US T-bill (`^IRX`) via yfinance, cached daily. Falls back to 4%.

**Edge cases:** Returns 0.0 if < 30 data points or zero standard deviation.

#### 4.6.5 Position Table (`position_table.py`)

##### `render_position_table(positions, currency_symbol, prices=None) -> None`

Renders a styled HTML table of all open positions.

**Columns:** Symbol, Name, Market, Qty, Avg Cost, Price, Value, P&L, P&L %

**Styling:** Green pills for gains, red for losses, monospace numbers, alternating row backgrounds, "—" for missing data.

---

### 4.7 Dashboard Views

#### Tab 1: Statistics View (`statistics_view.py`)

##### `render(portfolio, prices, price_date="") -> None`

Two-column layout: statistics on the left, charts on the right.

**Left Column:**
- **Portfolio Summary** (6 metric cards): Total Value, Cash, P&L, P&L %, Realized P&L, Avg Holding Days
- **Position Counts**: NIS Stocks, USD Stocks, Open Options
- **Performance vs Benchmarks** (HTML table): Total Return, CAGR, Max Drawdown, Sharpe for portfolio + S&P 500 + TA-125
- **Top 5 Gainers / Losers**: Sorted by P&L %
- **Currency Exposure**: NIS vs USD weight percentages

**Right Column:**
- **Treemap**: Portfolio composition colored by P&L %
- **P&L Bar Chart**: Unrealized P&L per position (TASE vs US colored)

#### Tab 2: Performance View (`performance_view.py`)

##### `render() -> None`

Comprehensive performance analysis with benchmark comparisons.

**Helper: `_stable_start_filter(series)`**
Removes leading data points with >10% day-over-day change to ensure stable baseline for metrics.

**Sections:**
1. **Metric Cards**: Total Return, CAGR, Max Drawdown, Sharpe Ratio
2. **Benchmark Labels**: S&P 500 and TA-125 Total Return + CAGR
3. **Chart 1**: Invested Capital Over Time (area chart)
4. **Chart 2**: Drawdown Underwater Plot
5. **Chart 3**: Book Value vs Benchmarks (indexed to 100)
6. **Chart 3b**: Market Value vs Benchmarks (if market data available)
7. **Chart 3c**: US vs TASE — Book Value Split (indexed to 100)
8. **Chart 3d**: US vs TASE — Market Value Split
9. **Chart 4**: Monthly Returns Bar (left column)
10. **Chart 5**: Rolling Sharpe Ratio (right column)

**Data sources:**
- `daily_portfolio_state` table for invested capital and market values
- `benchmark_fetcher` for S&P 500 and TA-125
- Prefers market value series over book value for metrics (when available)

#### Tabs 3–4: Portfolio View (`portfolio_view.py`)

##### `render(positions, prices, currency_symbol, cash, title) -> None`

Single-market portfolio display (one for TASE ₪, one for US $).

**Layout:**
1. **Summary Metrics**: Invested, Market Value, P&L, P&L %
2. **Cash Balance Card**
3. **Two Charts**: Allocation Pie (left) + P&L Bar (right)
4. **Position Table**: Full styled HTML table

#### Tab 5: Merged View (`merged_view.py`)

##### `render(portfolio, prices, price_date="") -> None`

All positions unified in NIS. USD positions converted via FX rate.

**FX Resolution:** DB lookup → current rate → fallback 3.7 with warning.

**Layout:**
1. **FX Rate Display**
2. **Summary Metrics** (in ₪): Total Invested, Market Value, P&L, P&L %
3. **Cash Cards**: NIS Cash, USD Cash (with ₪ conversion), Total Cash
4. **Two Charts**: Allocation Pie + P&L Bar (TASE vs US colored)
5. **Merged Position Table**: All positions with values in ₪

#### Tab 6: Options View (`options_view.py`)

##### `render(options_nis, options_usd) -> None`

Options positions with direction classification.

**Direction Logic:**
- **LONG**: quantity > 0.001
- **SHORT**: quantity < −0.001
- **CLOSED**: |quantity| < 0.001

**Controls:**
- Toggle "Open positions only" (default: on)
- Toggle "Interactive table" (default: off — uses HTML table)

**Layout:**
1. **Summary Metrics**: Total Positions, Long/Short count, Total Capital
2. **Position Table**: Symbol, Name, Currency, Direction (badge), Qty, Avg Cost, Total Invested

---

## 5. Financial Theory Reference

### Cumulative Returns (Indexed to 100)

Normalizes a price series so all portfolios start at the same value (100), making percentage comparison straightforward regardless of initial investment size.

```
Index(t) = (Value(t) / Value(0)) × 100
```

If the index reads 135, the portfolio has gained 35% since inception.

### CAGR (Compound Annual Growth Rate)

The hypothetical constant annual growth rate that would produce the same final result. Smooths out volatility.

```
CAGR = (End / Start) ^ (1/Years) − 1
```

A portfolio growing from ₪100k to ₪150k over 3 years has CAGR ≈ 14.5%.

### Maximum Drawdown

The largest peak-to-trough percentage decline. Measures the worst-case loss an investor would have experienced.

```
Drawdown(t) = (Value(t) − RunningMax(t)) / RunningMax(t)
Max DD = min(Drawdown) over all t
```

A max drawdown of −30% means at the worst point, the portfolio was 30% below its prior peak.

### Sharpe Ratio

Measures excess return per unit of volatility. Higher is better.

```
Sharpe = (Mean(R − Rf) / Std(R − Rf)) × √252
```

Where R = daily returns, Rf = daily risk-free rate, 252 = trading days per year.

### Drawdown (Underwater) Plot

A time-series chart showing how far below the running peak the portfolio sits at each point. Values are always ≤ 0%. Deeper dips = larger losses from peak. Recovery to 0% = new all-time high.

### Average Cost Basis

The weighted average purchase price per share:

```
Avg Cost = Total Invested / Quantity
```

Updated on each buy (increase both numerator and denominator) and sell (reduce both proportionally).

### Realized vs Unrealized P&L

- **Unrealized P&L**: Gain/loss on open positions = `(Current Price − Avg Cost) × Quantity`
- **Realized P&L**: Gain/loss from closed trades = `Qty Sold × (Sale Price − Avg Cost at time of sale)`

---

## 6. Caching & Performance

### Cache Layers

| Cache | Storage | TTL | Invalidation |
|-------|---------|-----|--------------|
| **Fast-Load Portfolio** | `portfolio_current` table (JSON) | Indefinite | New import (`is_portfolio_stale()`) |
| **Price Cache** | `price_cache` table | Indefinite | Manual refresh button |
| **FX Rates** | `fx_rates` table | Indefinite | Never (historical rates don't change) |
| **Benchmark Prices** | `benchmark_cache` table | Indefinite | Incremental fetch for new dates |
| **TASE Symbol Map** | `tase_symbol_map` table + runtime dict | Indefinite | Never (symbols rarely change) |
| **Risk-Free Rate** | `metadata` table | 1 day | Auto-refreshes daily |
| **Streamlit Caches** | In-memory (`@st.cache_data`) | Session | `st.cache_data.clear()` |

### Fast-Load Cache Flow

```
App Start
    │
    ├─ is_portfolio_stale()?
    │   ├─ NO  → load_portfolio_current() → skip build
    │   └─ YES → build() → save_portfolio_current()
    │
    ▼
Dashboard renders with cached portfolio
```

### Row Deduplication

Each Excel row gets a SHA-256 hash. On insert, `INSERT OR IGNORE` skips rows with matching hashes. This prevents duplicate imports from corrupting the portfolio.

---

## 7. IBI Broker Quirks & Fixes

| Quirk | Problem | Fix in Code |
|-------|---------|-------------|
| **Agorot Prices** | TASE prices in 1/100 shekel | `normalize_price()` ÷ 100 for TASE |
| **API Agorot** | Some APIs also return agorot | `_normalize_tase()` auto-detects and divides |
| **Option Expiry Order** | Credit appears after sell on same date | `_reorder_options_expiry()` adjusts sort keys |
| **Phantom Transactions** | Internal entries (taxes, forex) look like real trades | `detect_phantom()` filters by symbol/name patterns |
| **NIS Cash Balance** | No initial balance in data | Uses IBI's own `balance` column directly |
| **Pre-Transfer Shares** | Sells reference shares bought before data starts | Auto-creates phantom shares at ₪0 cost basis |
| **Hebrew Column Names** | All columns in Hebrew | `COLUMN_MAP` translates to English |
| **Date Format** | DD/MM/YYYY | Parsed to YYYY-MM-DD |
| **Dual-Listed Stocks** | NIS currency but US market | Detected by ticker pattern (1–6 uppercase letters) |

---

## 8. Test Suite

88 tests across 4 files:

| File | Tests | Coverage |
|------|-------|----------|
| `test_builder.py` | Portfolio build algorithm | Buy/sell/split/deposit flows, position tracking, cash balances, realized P&L |
| `test_classifier.py` | Transaction classification | Phantom detection, 21 types, price normalization, agorot conversion |
| `test_performance_metrics.py` | Metric calculations | CAGR, max drawdown, Sharpe ratio, cumulative returns |
| `test_repository.py` | Database CRUD | Insert, fetch, dedup, cache operations |

**Run tests:**
```bash
pytest tests/ -v
```

---

*Generated 2026-03-10 for Portfolio Dashboard v1.x*
