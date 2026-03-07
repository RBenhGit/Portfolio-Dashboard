# IBI Portfolio Dashboard

A Streamlit-based investment portfolio dashboard that reconstructs and tracks a multi-market portfolio from IBI broker (Israel) transaction exports. It processes 2,000+ raw Hebrew-labeled transactions, handles 21 transaction types with IBI-specific quirks (agorot pricing, phantom entries, option expiry reordering), and delivers 6 interactive tabs with 9 chart types, multi-currency accounting, and benchmark comparison against S&P 500 and TA-125.

---

## Why

### The Problem

Israeli investors using **IBI** (a leading Israeli brokerage) face a significant gap: the broker provides raw transaction exports in Excel with Hebrew labels, 21 distinct transaction types, prices in agorot (1/100 shekel), phantom internal entries, and no unified portfolio view across markets. Manually tracking holdings, cost basis, realized P&L, and multi-currency performance across both the **Tel Aviv Stock Exchange (TASE)** and **US equity markets** is error-prone and time-consuming.

### What This Dashboard Solves

| Pain Point | Previous Manual Approach | Dashboard Solution |
|-----------|--------------------------|-------------------|
| **Transaction classification** | Manually map 21 Hebrew types | Automated classifier recognizes all types + cost basis |
| **Agorot conversion** | Error-prone mental math (÷100) | Normalized at ingestion boundary |
| **Multi-currency P&L** | Spreadsheet formulas with date-lookup | Historical FX rates cached per transaction date |
| **Portfolio reconstruction** | Start from scratch each time | Deduplicated, incremental inserts; sequential builder pass |
| **Unrealized vs realized** | Manual tracking spreadsheets | Automated calculations per position per sell |
| **Phantom filtering** | Delete suspicious rows manually | Regex pattern detection + symbol-based filtering |
| **Performance metrics** | No baseline (CAGR, Sharpe, etc.) | Built-in vs S&P 500 and TA-125 comparison |
| **Options handling** | Treat like stocks, causes errors | Short-sell support, expiry reordering fix |
| **Pre-transfer shares** | Unknown initial positions | Auto-phantom adjustment for shortfalls |

### IBI Broker Quirks & Design Decisions

| Quirk | Design Decision | Trade-off |
|-------|----------------|-----------|
| **Agorot pricing** — TASE prices in 1/100 shekel | Convert all TASE prices ÷100 at ingestion boundary | Detection logic required for API prices; one-time conversion at boundaries |
| **21 Hebrew transaction types** | Broker-agnostic classifier interface (`BaseClassifier` ABC) with IBI-specific implementation | Allows future broker integrations without touching builder/dashboard |
| **Phantom entries** — tax accounts (999*), forex (99028), settlement (5039813) | Mark `is_phantom=1` in DB, filter at query time | Preserves audit trail; allows re-examination if detection logic is wrong |
| **Option expiry reordering** — IBI records sell before credit | Reorder sort keys to process credits before sells | Transparent to downstream; sort key is string-based |
| **Pre-transfer missing shares** — sells exceed available qty | Auto-fill shortfall at cost basis ₪0 | Early positions have artificially depressed cost basis |
| **Stock splits (הטבה)** — ambiguous: split if price=0, bonus if price>0 | Inspect execution price to classify | Heuristic; breaks if IBI records split with non-zero price |
| **Historical FX rates** — reference date is last transaction date | Store per-date rates; no live FX for valuations | Reproducible valuations tied to data; no daily fluctuation surprises |
| **Same-date ordering** — buys and sells on same date | Process "add" before "remove" via sort key priority | Prevents false insufficient-shares errors |

---

## What

### Dashboard Tabs (6)

| Tab | Name | Layout | Key Content |
|-----|------|--------|-------------|
| 1 | **Statistics** | Two-column (1/3 stats, 2/3 charts) | Portfolio summary (6 metric cards), performance metrics table (vs benchmarks), top 5 gainers/losers, currency exposure, treemap composition, P&L breakdown bar |
| 2 | **Performance** | Full-width, 6 charts | Total Return, CAGR, Max Drawdown, Sharpe Ratio metric cards; benchmark captions; area chart, drawdown, cumulative returns vs benchmarks, monthly returns bar, rolling Sharpe, monthly heatmap |
| 3 | **TASE (₪)** | Full-width | NIS positions with cash card, donut pie allocation, P&L bar chart, styled position table |
| 4 | **US ($)** | Full-width | USD positions with cash card, donut pie allocation, P&L bar chart, styled position table |
| 5 | **Merged (₪)** | Full-width | All positions in shekels (FX-converted), 3 cash cards (NIS, USD, total), unified pie + P&L bar, position table colored by market |
| 6 | **Options** | Full-width | Open/closed options with direction badges (LONG/SHORT/CLOSED), summary metrics, toggle for interactive table |

### Charts (9 Plotly Functions)

| Chart | Function | Height | Description |
|-------|----------|--------|-------------|
| Allocation Donut Pie | `allocation_pie()` | 380px | Market value allocation with 35% hole, percent+label inside |
| P&L Horizontal Bar | `pnl_bar()` | auto | Color-coded gain/loss bars with currency labels |
| Portfolio Treemap | `allocation_treemap()` | 450px | Hierarchical allocation colored by P&L %, multi-currency |
| P&L Waterfall | `waterfall_pnl()` | 400px | Cumulative P&L with running total |
| Area with Gradient | `area_chart_with_gradient()` | 420px | Portfolio value over time with gradient fill |
| Drawdown Underwater | `drawdown_chart()` | 250px | Red underwater plot showing peak-to-trough decline |
| Monthly Returns Heatmap | `monthly_returns_heatmap()` | auto | Calendar-style year×month grid colored by return % |
| Monthly Returns Bar | `monthly_returns_bar()` | 350px | Monthly returns with color-coded gain/loss bars |
| Rolling Sharpe | `rolling_sharpe_chart()` | 300px | 60-day rolling Sharpe with average line and reference lines |

### Performance Metrics

| Metric | Formula | Notes |
|--------|---------|-------|
| Total Return | `(end / start - 1) × 100` | Cost basis + realized P&L only |
| CAGR | `(end / start)^(1/years) - 1` | Uses 365.25 days/year |
| Max Drawdown | `min((series - cummax) / cummax)` | Peak-to-trough decline % |
| Sharpe Ratio | `mean(excess) / std(excess) × √252` | 4% risk-free rate, min 30 data points |

### Supported Transaction Types (21)

| Category | Types | Effect |
|----------|-------|--------|
| **Buys** | קניה שח, קניה רצף, קניה מעוף, קניה חול מטח | Add shares, debit cash |
| **Sells** | מכירה שח, מכירה רצף, מכירה מעוף, מכירה חול מטח | Remove shares, credit cash, record realized P&L |
| **Transfers** | הפקדה (deposit), משיכה (withdrawal) | Share transfer in/out |
| **Options** | הפקדה פקיעה (expiry credit), משיכה פקיעה (expiry debit) | Option settlement with auto-reordering |
| **Splits/Bonus** | הטבה (price=0 → split, price>0 → bonus) | Adjust quantity, preserve cost basis |
| **Dividends** | דיבידנד, הפקדה דיבידנד מטח | Cash inflow (NIS or USD) |
| **Fees/Tax** | דמי טפול, משיכת מס חול מטח, משיכת מס מטח, משיכת ריבית מטח | Cash outflow (phantom) |
| **Other** | ריבית מזומן בשח (interest), העברה מזומן בשח (transfer) | Cash movements |

### Sidebar Controls

- **API Status** — Twelvedata: Connected / Unavailable indicator
- **Import Transactions** — File uploader for new `.xlsx` files (deduplicates automatically)
- **Last Import Info** — Filename, timestamp, rows added
- **Force Re-parse Excel** — Re-process the configured Excel file
- **Refresh Prices** — Clear price cache and fetch current market data
- **Database Info** — Path to `.db`, total transaction count

### Limitations

- Portfolio value is **cost basis + realized P&L only** — unrealized gains/losses are shown separately per position but not in the Performance tab's historical series
- Performance charts end at the **last transaction date**, not today's date
- Sharpe Ratio uses a **hardcoded 4% risk-free rate** and requires ≥30 data points
- Only **2 benchmarks** supported (S&P 500, TA-125); adding more requires editing `BENCHMARKS` dict
- FX conversion uses the rate from the portfolio state snapshot, not live rates
- Options are not priced (no market price fetching for options)
- Pre-transfer phantom shares are created at cost basis ₪0

---

## How

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Streamlit Dashboard (app.py) — 6 tabs                       │
│  statistics_view, performance_view, portfolio_view,           │
│  merged_view, options_view                                   │
│  theme, styles, charts, position_table, performance_metrics  │
├──────────────────────────────────────────────────────────────┤
│  Portfolio Engine                                            │
│  builder.py (sequential build + fast-load cache)             │
│  + price_fetcher.py                                          │
├──────────────────────────────────────────────────────────────┤
│  Classification & Enrichment                                 │
│  ibi_classifier.py (21 types) + symbol_mapper.py             │
├──────────────────────────────────────────────────────────────┤
│  Market Data                                                 │
│  price_fetcher.py + fx_fetcher.py + benchmark_fetcher.py     │
├──────────────────────────────────────────────────────────────┤
│  Data Access (repository.py) + SQLite (db.py, 12 tables)     │
├──────────────────────────────────────────────────────────────┤
│  Input (excel_reader.py) + FX (fx_fetcher.py)                │
├──────────────────────────────────────────────────────────────┤
│  Domain Models: Transaction, Position (dataclasses)          │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

```
IBI Excel (.xlsx)
    │
    ▼
Excel Reader ─── Parse Hebrew headers, sort by date, compute SHA256 row hash
    │
    ▼
IBI Classifier ── Classify 21 transaction types → effect + direction + cash flows
    │               Detect phantoms, normalize agorot prices (÷100)
    ▼
FX Fetcher ────── Fetch historical USD/ILS rates for all transaction dates
    │               Primary: Twelvedata API │ Fallback: yfinance
    ▼
Repository ────── Deduplicated insert (INSERT OR IGNORE by row_hash)
    │
    ▼
Portfolio Builder ── Sequential pass over all transactions:
    │                  • Reorder option expiry (fix IBI ordering bug)
    │                  • Process buys/sells/splits/deposits chronologically
    │                  • Track NIS and USD positions separately
    │                  • Record daily portfolio state snapshots
    │                  • Calculate realized P&L on each sell
    ▼
Price Fetcher ──── Fetch closing prices for open positions
    │                Primary: Twelvedata │ Fallback: yfinance
    ▼
Streamlit Dashboard ── Render 6 tabs with metrics, tables, and charts
    Tab 1: Statistics — portfolio summary, performance, top gainers/losers
    Tab 2: Performance — historical returns vs benchmarks (6 charts)
    Tab 3: TASE (₪) — NIS positions
    Tab 4: US ($) — USD positions
    Tab 5: Merged (₪) — all positions in shekels
    Tab 6: Options — open options positions
```

### Key Algorithms

**Sequential Portfolio Build** ([builder.py](src/portfolio/builder.py)) — Processes every transaction chronologically in a single pass, maintaining position maps (`positions_nis`, `positions_usd`), cash balances, and cumulative realized P&L. Each sell calculates `realized_pnl = qty × (sale_price - avg_cost)` and proportionally reduces cost basis. NIS cash uses IBI's own running balance column; USD cash is accumulated from cash flow transactions.

**Stock Split Handling** — IBI records splits as the number of NEW shares added (הטבה with price=0). The builder computes `new_quantity = current + added`, keeping `total_invested` unchanged so average cost adjusts automatically: `ratio = (pos.quantity + qty_abs) / pos.quantity`.

**Option Expiry Reordering** ([builder.py:21-51](src/portfolio/builder.py#L21-L51)) — IBI records expiry credits (הפקדה פקיעה) after sells on the same date. The builder adjusts sort keys to process credits first (`date_0` for adds, `date_1` for removes), preventing false insufficient-shares errors.

**Pre-Transfer Phantom Shares** — When a sell exceeds available quantity for a non-option position, the builder auto-fills the shortfall at cost basis ₪0. This handles shares that were bought before the IBI data begins and transferred in later.

**TASE Symbol Resolution** ([symbol_mapper.py](src/market/symbol_mapper.py)) — IBI uses 5-8 digit numeric IDs for TASE stocks. Resolution chain: runtime cache → DB cache → static map (12 known stocks) → Twelvedata `symbol_search` API → fallback to None.

**Stabilization Detection** ([performance_view.py:46-56](src/dashboard/views/performance_view.py#L46-L56)) — Auto-trims the initial account build-up period where bulk imports create >10% daily swings. Uses `pct_change().abs() <= 0.10` to find the first stable day and slices the series from there.

**Fast-Load Cache** ([repository.py](src/database/repository.py), [builder.py](src/portfolio/builder.py)) — After each full build, the result (positions, cash, P&L) is serialized to JSON and stored in the `portfolio_current` table. On app startup, `is_portfolio_stale()` compares `built_at` against the latest `import_log` entry. If no new imports occurred, the cached result is returned instantly, skipping the full sequential rebuild. Position objects are serialized via `to_snapshot_dict()` and reconstructed via `Position.from_dict()`.

**Benchmark Caching** ([benchmark_fetcher.py](src/market/benchmark_fetcher.py)) — S&P 500 and TA-125 prices cached in SQLite `benchmark_cache` table. Fetcher checks cached date ranges and only requests missing periods from yfinance, minimizing API calls. Failures degrade gracefully (logged as warnings).

### Database Schema (SQLite, 12 tables)

| Table | Purpose |
|-------|---------|
| `transactions` | Classified transaction ledger (26 columns, deduped by `row_hash`) |
| `fx_rates` | Historical USD/ILS rates by date |
| `price_cache` | Market prices by (symbol, market, price_date) |
| `metadata` | App-wide key-value store (file mtime, last parse, etc.) |
| `daily_portfolio_state` | End-of-day portfolio snapshot (invested, cash, P&L, market values) |
| `realized_trades` | Per-sell trade details with P&L |
| `portfolio_snapshots` | Point-in-time portfolio summaries |
| `position_snapshots` | Holdings within each snapshot |
| `tase_symbol_map` | IBI numeric ID → Twelvedata/yfinance ticker cache |
| `import_log` | Import history (file, timestamp, rows added/duped) |
| `benchmark_cache` | S&P 500 and TA-125 index prices for performance comparison |
| `portfolio_current` | Serialized build result for fast app startup (avoids full rebuild) |

### Technology Stack

| Component | Technology |
|-----------|-----------|
| Web UI | Streamlit >=1.32.0 |
| Data Processing | pandas >=2.1.0 |
| Excel I/O | openpyxl >=3.1.2 |
| Charts | Plotly >=5.18.0 |
| Database | SQLite3 (WAL mode, built-in) |
| Price Data | Twelvedata (primary) + yfinance >=0.2.66 (fallback) |
| HTTP | requests >=2.31.0 |
| Config | python-dotenv >=1.0.0 |

### Color Theme

| Semantic | Hex | Usage |
|----------|-----|-------|
| Profit | `#10B981` | Positive P&L, gains |
| Loss | `#EF4444` | Negative P&L, losses |
| Accent Primary | `#6366F1` | Portfolio line, headers, TASE |
| S&P 500 | `#F59E0B` | Amber dashed benchmark |
| TA-125 | `#EC4899` | Pink dashed benchmark |
| Background | `#FAFBFE` | Page background |
| Text Primary | `#1E293B` | Main text |

---

## Getting Started

### Prerequisites

- Python 3.10+
- An IBI broker transaction export (`.xlsx` file)

### Installation

```bash
cd Portfolio_Dashboard
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```bash
TWELVEDATA_API_KEY=your_api_key_here    # Sign up at twelvedata.com (free tier: 800 calls/day)
YFINANCE_ENABLED=true                    # Free fallback, no API key needed
```

### Input Data

Place your IBI Excel export at:

```
Portfolio_Dashboard/Trans_Input/Transactions_IBI.xlsx
```

The file should contain the standard IBI transaction export columns (Hebrew headers are auto-mapped).

### Run

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

### Importing New Data

- **Upload via sidebar**: Click "Browse Files" under "Import Transactions" to upload a new `.xlsx` file. Duplicate rows are automatically skipped.
- **Force re-parse**: Click "Force Re-parse Excel" to re-process the configured Excel file.
- **Refresh prices**: Click "Refresh Prices" to clear the price cache and fetch current market data.

---

## Project Structure

```
Portfolio_Dashboard/
├── app.py                          # Streamlit entry point (6 tabs)
├── requirements.txt                # Python dependencies
├── .env                            # API keys (not in repo)
├── docs/                           # Project documentation
│   ├── performance-tab-why-how-what.md
│   ├── Insufficient_Shares_Investigation_2026-02-20.md
│   └── 2000_api_guide_eng.pdf      # IBI API reference
├── tests/                          # Test suite (91 tests)
│   ├── test_builder.py             # Portfolio build logic tests
│   ├── test_classifier.py          # Transaction classification tests
│   ├── test_performance_metrics.py # Metric calculation tests
│   └── test_repository.py          # Database CRUD tests
├── Trans_Input/
│   └── Transactions_IBI.xlsx       # IBI broker export
├── data/
│   └── portfolio.db                # SQLite database (auto-created)
└── src/
    ├── config.py                   # Paths, API keys, constants
    ├── models/
    │   ├── transaction.py          # Transaction dataclass
    │   └── position.py             # Position dataclass
    ├── input/
    │   └── excel_reader.py         # IBI Excel parsing & normalization
    ├── classifiers/
    │   ├── base_classifier.py      # Abstract classifier interface
    │   └── ibi_classifier.py       # 21 IBI transaction type classifier
    ├── market/
    │   ├── symbol_mapper.py        # TASE ID → ticker resolution
    │   ├── price_fetcher.py        # Market price fetching & caching
    │   ├── fx_fetcher.py           # USD/ILS historical rate fetching
    │   └── benchmark_fetcher.py    # S&P 500 & TA-125 via yfinance + cache
    ├── portfolio/
    │   ├── ingestion.py            # Full pipeline orchestration
    │   └── builder.py              # Sequential portfolio build loop
    ├── database/
    │   ├── db.py                   # SQLite schema (12 tables, WAL mode)
    │   └── repository.py           # Data access layer (CRUD)
    └── dashboard/
        ├── theme.py                # Color palette, Plotly template (ibi_dark)
        ├── styles.py               # CSS stylesheet + HTML helpers (metric_card_html, html_table)
        ├── components/
        │   ├── charts.py           # 9 Plotly chart functions (pie, bar, treemap, waterfall, area, drawdown, heatmap, monthly bar, rolling Sharpe)
        │   ├── position_table.py   # Styled HTML position table
        │   └── performance_metrics.py # CAGR, Sharpe, max drawdown, cumulative returns
        └── views/
            ├── statistics_view.py  # Tab 1: Two-column layout — stats + charts
            ├── performance_view.py # Tab 2: 6 charts + benchmark comparison
            ├── portfolio_view.py   # Tabs 3-4: Single-market (TASE or US)
            ├── merged_view.py      # Tab 5: All positions in ₪
            └── options_view.py     # Tab 6: Open options with long/short badges
```
