# Performance Tab — Why · How · What

The Performance tab (Tab 2) provides historical portfolio performance tracking with benchmark comparison for an IBI brokerage portfolio. It computes key financial metrics (Total Return, CAGR, Max Drawdown, Sharpe Ratio) and renders **six interactive Plotly charts** — portfolio value area chart with gradient fill, drawdown underwater plot, cumulative returns vs S&P 500 and TA-125, monthly returns bar chart, rolling Sharpe ratio (60-day window), and monthly returns heatmap. A stabilization detection algorithm automatically skips the initial account build-up period where bulk imports distort the data. The tab displays **only actual historical data** with no forward-looking projections.

---

## Why

### Problem

When a user first imports their IBI transaction history, the first several days contain **bulk deposit transactions** (`הפקדה`) representing pre-existing holdings being ingested into the system. This creates massive artificial day-over-day swings:

| Date | Portfolio Value | Day-over-Day Change |
|------|----------------|---------------------|
| May 1, 2022 | ₪99,000 | — (first entry) |
| May 2, 2022 | ₪111,000 | +12% |
| May 6, 2022 | ₪182,000 | +64% |
| May 8, 2022 | ₪182,500 | ~0% (stable) |

These aren't real investment returns — they're account setup noise. Without filtering, Total Return was inflated to **+422.7%** and the charts showed misleading spikes in the bottom-left corner.

### Who It Serves

Israeli individual investors using IBI as their broker who want to see **actual investment performance**, not account migration artifacts.

### Previous Approach

The original code simply skipped zero/negative values and started from the first positive entry. This did not address the build-up period where values are positive but artificially volatile.

An earlier version also injected the current live market value as today's data point (forward-looking extrapolation). This was **removed** because:

1. **Methodological inconsistency** — The historical series was cost basis + realized P&L, but live market value includes unrealized gains. Mixing the two produced a misleading final data point.
2. **Visual distortion** — A jump from the last stored daily state to today's live value appeared as a projection/extrapolation on the charts.
3. **Philosophical clarity** — The tab now shows purely historical data, consistent with the stated disclaimer. Performance metrics (Total Return, CAGR, Sharpe, Max Drawdown) use the **market value series** (mark-to-market) when available, falling back to book value when price data is insufficient.

### Design Decisions

| Decision | Choice | Trade-off |
|----------|--------|-----------|
| Threshold | 10% day-over-day | Low enough to catch bulk imports, high enough to preserve real volatile days |
| Detection | First stable day wins | Simple, no multi-day confirmation needed — once imports stop, trading is real |
| Direction | Absolute value of % change | Both +15% and -15% swings are treated equally |
| Fallback | If no stable day found, keep all data | Avoids empty charts for edge cases |
| Valuation | Market value (mark-to-market) for metrics; book value for "Invested Capital" charts | Metrics reflect actual portfolio performance; book-value charts show capital deployed |
| Fallback | If market value data is insufficient (< 2 points), fall back to book value | Ensures metrics are always available even without price data |
| No extrapolation | Charts end at last stored daily state | Avoids mixing live market data with historical series |

---

## How

### Architecture

```
┌──────────────────────────┐
│ SQLite: daily_portfolio_  │
│ state table (db.py)      │
└──────────┬───────────────┘
           │ repository.get_daily_portfolio_states()
           ▼
┌──────────────────────────┐     ┌───────────────────────────┐
│ performance_view.py      │────▶│ benchmark_fetcher.py      │
│  • Aggregation           │     │  • yfinance + SQLite cache│
│  • Stabilization         │     │  • S&P 500, TA-125       │
│  • Metrics               │     └───────────────────────────┘
│  • 6 Charts              │
└──────────┬───────────────┘
           │ calls
           ▼
┌──────────────────────────┐     ┌───────────────────────────┐
│ performance_metrics.py   │     │ charts.py                 │
│  • compute_cagr          │     │  • area_chart_with_       │
│  • compute_max_drawdown  │     │    gradient               │
│  • compute_sharpe_ratio  │     │  • drawdown_chart         │
│  • compute_cumulative_   │     │  • monthly_returns_bar    │
│    returns               │     │  • monthly_returns_       │
└──────────────────────────┘     │    heatmap                │
                                 │  • rolling_sharpe_chart   │
                                 └───────────────────────────┘
```

### Data Flow

1. **Load** — `repository.get_daily_portfolio_states()` ([repository.py:217-224](src/database/repository.py#L217-L224)) queries `daily_portfolio_state` ordered by date
2. **Aggregate** — Two series are built from daily state rows: a **book-value series** (`total_cost_nis + cum_realized_pnl_nis + cum_realized_pnl_usd × fx_rate`) for "Invested Capital" charts, and a **market-value series** (`total_market_value_nis`) for performance metrics. The market-value series is preferred for headline metrics (Total Return, CAGR, Sharpe, Drawdown); book value is used as fallback when market data is insufficient.
3. **Filter** — Stabilization detection trims the leading build-up period ([performance_view.py:35-47](src/dashboard/views/performance_view.py#L35-L47))
4. **Benchmark** — Fetch S&P 500 and TA-125 from Yahoo Finance with SQLite caching ([benchmark_fetcher.py:15-47](src/market/benchmark_fetcher.py#L15-L47))
5. **Compute** — Calculate Total Return, CAGR, Max Drawdown, Sharpe Ratio ([performance_metrics.py](src/dashboard/components/performance_metrics.py))
6. **Render** — Six Plotly charts + metric cards via Streamlit

### Stabilization Detection Algorithm

```python
# performance_view.py lines 46-56
portfolio_series = portfolio_series[portfolio_series > 0]       # drop zeros
pct_change = portfolio_series.pct_change().abs()                # daily % change
stable_mask = pct_change <= 0.10                                # ≤10% = stable
if stable_mask.any():
    first_stable = stable_mask.idxmax()                         # first True
    portfolio_series = portfolio_series.loc[first_stable:]      # trim
```

`pct_change().abs()` computes `|current - previous| / previous`. `idxmax()` on a boolean Series returns the index of the first `True`. The series is sliced from that date onward.

### Key Metric Formulas

| Metric | Formula | File:Line |
|--------|---------|-----------|
| Total Return | `(end / start - 1) × 100` | [performance_view.py:65](src/dashboard/views/performance_view.py#L65) |
| CAGR | `(end / start)^(1/years) - 1` using 365.25 days/year | [performance_metrics.py:13-28](src/dashboard/components/performance_metrics.py#L13-L28) |
| Max Drawdown | `min((series - cummax) / cummax)` | [performance_metrics.py:31-37](src/dashboard/components/performance_metrics.py#L31-L37) |
| Sharpe Ratio | `mean(excess) / std(excess) × √252`, risk-free = 4%, min 30 points | [performance_metrics.py:40-57](src/dashboard/components/performance_metrics.py#L40-L57) |

### Benchmark Caching

Benchmark prices are cached in `benchmark_cache` table ([db.py:153-159](src/database/db.py#L153-L159)). The fetcher checks cached date ranges and only requests missing periods from yfinance, minimizing API calls. Failures are logged as warnings but do not stop execution (graceful degradation).

### Database Schema

**Daily Portfolio State** ([db.py:106-118](src/database/db.py#L106-L118)):

| Column | Type | Description |
|--------|------|-------------|
| `date` | TEXT (PK) | Transaction date |
| `total_cost_nis` | REAL | `(nis_invested + nis_cash) + (usd_invested + usd_cash) × fx_rate` (book value) |
| `cum_realized_pnl_nis` | REAL | Cumulative P&L from closed NIS positions |
| `cum_realized_pnl_usd` | REAL | Cumulative P&L from closed USD positions |
| `fx_rate` | REAL | USD/ILS rate on that date (fallback: 3.7) |
| `nis_market_value` | REAL | `sum(price × qty)` for NIS positions (mark-to-market) |
| `usd_market_value` | REAL | `sum(price × qty)` for USD positions (mark-to-market) |
| `total_market_value_nis` | REAL | `(nis_mv + nis_cash) + (usd_mv + usd_cash) × fx_rate` — **used for performance metrics** |

**Benchmark Cache** ([db.py:153-159](src/database/db.py#L153-L159)):

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | TEXT | yfinance ticker (e.g. `^GSPC`) |
| `date` | TEXT | Price date |
| `close` | REAL | Closing price |
| `fetched_at` | TEXT | Timestamp of when data was fetched |

---

## What

### Features

1. **4 Metric Cards** — Total Return, CAGR, Max Drawdown, Sharpe Ratio displayed in a row
2. **Benchmark Captions** — Total Return and CAGR for each benchmark shown below the cards (colored labels)
3. **Portfolio Value Chart** — Area chart with gradient fill showing portfolio value (₪) over time (420px)
4. **Drawdown Chart** — Underwater/drawdown plot with red fill (250px)
5. **Cumulative Returns Chart** — Base-100 normalized chart comparing portfolio (indigo solid) vs S&P 500 (amber dashed) and TA-125 (pink dashed) (450px)
6. **Monthly Returns Bar + Rolling Sharpe** — Side-by-side: monthly returns bar chart (350px) and 60-day rolling Sharpe ratio with average line (300px)
7. **Monthly Returns Heatmap** — Calendar-style year×month grid colored by return percentage
8. **Auto Build-Up Detection** — Automatically skips initial import period (>10% daily swings)
9. **Benchmark Caching** — SQLite cache for S&P 500 and TA-125 prices
10. **Historical Data Only** — No forward-looking projections; charts end at the last stored daily state

### Supported Benchmarks

| Name | Symbol | Style in Chart |
|------|--------|----------------|
| S&P 500 | `^GSPC` | Amber dashed (`#F59E0B`) |
| TA-125 | `^TA125.TA` | Pink dashed (`#EC4899`) |

### Inputs

| Input | Source | Description |
|-------|--------|-------------|
| `daily_portfolio_state` rows | SQLite DB | Historical daily portfolio snapshots |
| Benchmark prices | Yahoo Finance / cache | S&P 500 and TA-125 closing prices |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| 4 metric cards | `st.metric` | Key performance indicators |
| Benchmark captions | `st.markdown` | Per-benchmark Total Return + CAGR (colored) |
| Portfolio Value chart | `area_chart_with_gradient()` | Area chart with fill, value in ₪ (420px) |
| Drawdown chart | `drawdown_chart()` | Underwater plot, red fill (250px) |
| Cumulative Returns chart | Plotly `go.Scatter` | Base-100 multi-line comparison (450px) |
| Monthly Returns bar | `monthly_returns_bar()` | Monthly returns, colored bars (350px) |
| Rolling Sharpe chart | `rolling_sharpe_chart()` | 60-day window with avg line (300px) |
| Monthly Returns heatmap | `monthly_returns_heatmap()` | Year×month calendar grid |
| Disclaimer caption | `st.caption` | Notes methodology differences between Invested Capital and Cumulative Returns charts |

### Configuration

| Setting | Value | Location |
|---------|-------|----------|
| Stabilization threshold | 10% daily change | `performance_view.py:53` |
| Risk-free rate | 4% annual | `performance_metrics.py` |
| Trading days/year | 252 | `performance_metrics.py` |
| Min points for Sharpe | 30 | `performance_metrics.py` |
| FX fallback rate | 3.7 ILS/USD | `builder.py` |
| Portfolio line color | `#6366F1` (indigo) | `theme.BM_PORTFOLIO` |
| Rolling Sharpe window | 60 days | `charts.rolling_sharpe_chart()` |

### Limitations

- Performance metrics use **market value** (mark-to-market) when price data is available, falling back to book value (cost basis + realized P&L) when insufficient prices are cached
- Charts end at the **last transaction date** in the database, not today's date
- Sharpe Ratio uses a **hardcoded 4% risk-free rate** and requires ≥30 data points
- Only **2 benchmarks** are supported; adding more requires editing `BENCHMARKS` dict in code
- FX conversion uses the rate from the portfolio state snapshot, not live rates
- CAGR uses calendar days (365.25), not trading days

### Error States

| Condition | Message |
|-----------|---------|
| No portfolio data | "No daily portfolio data yet. Import transactions first." |
| No positive values | "Portfolio has no positive values to display." |
| < 2 data points | "Not enough data points for performance analysis." |
