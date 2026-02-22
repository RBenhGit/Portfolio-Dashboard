# IBI Portfolio Dashboard

A Streamlit-based investment portfolio dashboard that reconstructs and tracks a multi-market portfolio from IBI broker (Israel) transaction exports.

---

## Why

Israeli investors using **IBI** (a leading Israeli brokerage) face a significant gap: the broker provides raw transaction exports in Excel with Hebrew labels, 21 distinct transaction types, prices in agorot (1/100 shekel), phantom internal entries, and no unified portfolio view across markets. Manually tracking holdings, cost basis, realized P&L, and multi-currency performance across both the **Tel Aviv Stock Exchange (TASE)** and **US equity markets** is error-prone and time-consuming.

This dashboard was built to:

- **Automate portfolio reconstruction** from 2,000+ raw broker transactions spanning May 2022 to present
- **Handle IBI's data quirks** — agorot pricing, Hebrew transaction types, phantom entries (tax/forex placeholders), option expiry ordering bugs, and pre-transfer missing shares
- **Provide multi-currency accounting** — track NIS and USD positions independently, with historically accurate FX rates (USD/ILS) for cost basis and current valuation
- **Deliver real-time insights** — unrealized P&L, allocation charts, realized trade history, and a unified portfolio view in shekels
- **Eliminate manual spreadsheet tracking** — one Excel upload produces a fully classified, priced, and visualized portfolio

---

## What

### Dashboard Features

| Feature | Description |
|---------|-------------|
| **Five portfolio tabs** | TASE (₪), US ($), Merged (all in ₪), Options, and Performance |
| **Position tracking** | Quantity, average cost, market price, market value, unrealized P&L (absolute and %) |
| **Cash balances** | NIS cash (from IBI's running balance) and USD cash (accumulated from forex transactions) |
| **Allocation charts** | Interactive donut pie charts showing market value distribution |
| **P&L charts** | Horizontal bar charts with color-coded gains (green) and losses (red) per position |
| **Merged view** | All positions converted to ₪ using historical FX rate for the reference date, with historical cost basis preserved |
| **Options view** | Open options positions separated by currency (NIS/USD), with long/short classification |
| **Performance analytics** | Total Return, CAGR, Max Drawdown, Sharpe Ratio with S&P 500 and TA-125 benchmark comparison |
| **Sidebar controls** | Upload new Excel files, force re-parse, refresh prices, view API status and import history |
| **Realized P&L** | Per-trade gain/loss tracking for every sell transaction |
| **Daily portfolio state** | Historical snapshots of invested amount, cash, and cumulative P&L for each transaction date |

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

### Special Handling

- **Option short selling** — options (8-digit symbols starting with 8 or 9) can go negative (short positions)
- **Pre-transfer positions** — shares bought before the data starts are auto-filled when a sell exceeds available quantity
- **Same-date ordering** — buys are processed before sells on the same date to prevent false insufficient-shares errors
- **Phantom filtering** — internal broker entries (tax accounts, forex placeholders) are excluded from positions

---

## How

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Streamlit Dashboard (app.py) — 5 tabs                       │
│  portfolio_view, merged_view, options_view, performance_view │
│  charts, position_table, performance_metrics                 │
├──────────────────────────────────────────────────────────────┤
│  Portfolio Engine                                            │
│  builder.py (sequential build) + price_fetcher.py            │
├──────────────────────────────────────────────────────────────┤
│  Classification & Enrichment                                 │
│  ibi_classifier.py (21 types) + symbol_mapper.py             │
├──────────────────────────────────────────────────────────────┤
│  Market Data                                                 │
│  price_fetcher.py + fx_fetcher.py + benchmark_fetcher.py     │
├──────────────────────────────────────────────────────────────┤
│  Data Access (repository.py) + SQLite (db.py, 11 tables)     │
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
Streamlit Dashboard ── Render 5 tabs with metrics, tables, and charts
    Tab 1: TASE (₪) — NIS positions
    Tab 2: US ($) — USD positions
    Tab 3: Merged (₪) — all positions in shekels
    Tab 4: Options — open options positions
    Tab 5: Performance — historical returns vs benchmarks
```

### Key Algorithms

**Sequential Portfolio Build** — processes every transaction chronologically, maintaining position maps (`positions_nis`, `positions_usd`), cash balances, and cumulative realized P&L. Each sell calculates `realized_pnl = qty × (sale_price - avg_cost)` and proportionally reduces cost basis.

**Stock Split Handling** — IBI records splits as the number of NEW shares added. The builder computes `new_quantity = current + added`, keeping `total_invested` unchanged so average cost adjusts automatically.

**Option Expiry Reordering** — IBI records expiry credits after sells of the same option on the same date. The builder adjusts sort keys to process credits first, preventing false insufficient-shares errors.

**TASE Symbol Resolution** — IBI uses 5-8 digit numeric IDs for TASE stocks. Resolution follows: runtime cache → DB cache → static map (7 known stocks) → Twelvedata symbol_search API → fallback to None.

### Database Schema (SQLite, 11 tables)

| Table | Purpose |
|-------|---------|
| `transactions` | Classified transaction ledger (26 columns, deduped by `row_hash`) |
| `fx_rates` | Historical USD/ILS rates by date |
| `price_cache` | Market prices by (symbol, market, price_date) |
| `metadata` | App-wide key-value store (file mtime, last parse, etc.) |
| `daily_portfolio_state` | End-of-day portfolio snapshot (invested, cash, P&L) |
| `realized_trades` | Per-sell trade details with P&L |
| `portfolio_snapshots` | Point-in-time portfolio summaries |
| `position_snapshots` | Holdings within each snapshot |
| `tase_symbol_map` | IBI numeric ID → Twelvedata/yfinance ticker cache |
| `import_log` | Import history (file, timestamp, rows added/duped) |
| `benchmark_cache` | S&P 500 and TA-125 index prices for performance comparison |

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
├── app.py                          # Streamlit entry point (5 tabs)
├── requirements.txt                # Python dependencies
├── .env                            # API keys (not in repo)
├── docs/                           # Project documentation
│   ├── performance-tab-why-how-what.md
│   ├── Insufficient_Shares_Investigation_2026-02-20.md
│   ├── Project_ReEvaluation_2026-02-20.md
│   └── 2000_api_guide_eng.pdf      # IBI API reference
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
    │   ├── db.py                   # SQLite schema (11 tables, WAL mode)
    │   └── repository.py           # Data access layer (CRUD)
    └── dashboard/
        ├── components/
        │   ├── charts.py           # Plotly pie & bar charts
        │   ├── position_table.py   # Styled position DataFrame
        │   └── performance_metrics.py # CAGR, Sharpe, max drawdown calculations
        └── views/
            ├── portfolio_view.py   # Single-market tab (TASE or US)
            ├── merged_view.py      # Combined all-in-₪ view
            ├── options_view.py     # Open options positions (NIS + USD)
            └── performance_view.py # Historical returns + benchmark comparison
```
