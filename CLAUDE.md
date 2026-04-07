# CLAUDE.md

## What This Is

Streamlit portfolio dashboard reconstructing investments from **IBI broker** (Israel) Excel exports. Tracks TASE/US positions separately, multi-currency (NIS/USD), historical prices, benchmark comparison.
More informations on the project: @docs\MASTER_PLAN.md

## Commands

```bash
streamlit run app.py
pytest
pytest tests/test_builder.py::test_buy_creates_position -v
pip install -r requirements.txt
```

## Architecture

```
IBI Excel (.xlsx) → excel_reader → IBIClassifier → repository (SQLite) → builder → price_fetcher → dashboard
```

- **Ingestion** (`src/portfolio/ingestion.py`): Orchestrates pipeline — Excel → classify → FX rates → DB → builder.
- **Classifier** (`src/classifiers/ibi_classifier.py`): Maps 21 Hebrew IBI tx types to normalized effects. Extends `BaseClassifier` ABC.
- **Builder** (`src/portfolio/builder.py`): Sequential pass over transactions. Separate `positions_nis`/`positions_usd` dicts. Handles splits, option short-sells, phantom fills, expiry reordering. Writes `daily_portfolio_state` and `realized_trades`.
- **Price Fetcher** (`src/market/price_fetcher.py`): Twelvedata primary, yfinance fallback. Caches in `price_cache` table.
- **Symbol Mapper** (`src/market/symbol_mapper.py`): Resolves IBI numeric IDs to tickers. Chain: runtime cache → DB → `_KNOWN_TASE_MAP` → Twelvedata search.
- **Dashboard**: `app.py` → 7 tabs (Statistics, Performance, TASE ₪, US $, Merged ₪, Options, Cash Flow). Views in `src/dashboard/views/`, components in `src/dashboard/components/`.
- **Database**: SQLite `data/portfolio.db`. Tables: `transactions`, `fx_rates`, `price_cache`, `metadata`, `daily_portfolio_state`, `realized_trades`, `portfolio_snapshots`, `position_snapshots`, `tase_symbol_map`, `import_log`, `benchmark_cache`, `portfolio_current`. Schema in `src/database/db.py`.
- **Position** dataclass (`src/models/position.py`): quantity, total_invested, total_invested_nis, computed average_cost.

## Critical Domain Knowledge

- **Agorot**: 100 agorot = 1 ₪. IBI stores TASE prices in agorot; `normalize_price()` divides by 100 at ingestion. yfinance `.TA` returns ILA (agorot) — `_normalize_tase()` divides by 100.
- **Multi-currency**: NIS/USD positions in separate dicts. "Merged" view converts to NIS via FX rates.
- **Market detection**: Numeric IBI IDs (5-8 digits) → TASE, unless in `_KNOWN_US_NUMERIC_IDS`. `$` suffix → US. Options: 8-digit IDs starting with 8 or 9.
- **Phantoms**: Internal IBI entries (tax 999*, forex 99028, settlement 5039813) — `is_phantom=1`, filtered in builder, included for cash.
- **Option expiry reordering**: `_reorder_options_expiry()` ensures sells process before credits on same date.

## Configuration

- `.env`: `TWELVEDATA_API_KEY`, `YFINANCE_ENABLED=true`
- Excel input: `Trans_Input/Transactions_IBI.xlsx`
- Initial positions: `config/initial_positions.json`
- New TASE stock: add to `_KNOWN_TASE_MAP` in `symbol_mapper.py`. US stock with numeric IBI ID: add to `_KNOWN_US_NUMERIC_IDS`.

## ReEvaluation
 - **Implimentation re-evaluation** the state of the app's implimentation is found in  @docs in a file called docs\Project_ReEvaluation_[Date of Evaluation].md