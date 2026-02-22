# Performance Tab — Why · How · What

The Performance tab provides historical portfolio performance tracking with benchmark comparison for an IBI brokerage portfolio. It computes key financial metrics (Total Return, CAGR, Max Drawdown, Sharpe Ratio) and renders two interactive Plotly charts — portfolio value over time and cumulative returns vs S&P 500 and TA-125. A stabilization detection algorithm automatically skips the initial account build-up period where bulk imports distort the data.

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

The original code ([performance_view.py:37-43](src/dashboard/views/performance_view.py#L37-L43)) simply skipped zero/negative values and started from the first positive entry. This did not address the build-up period where values are positive but artificially volatile.

### Design Decisions

| Decision | Choice | Trade-off |
|----------|--------|-----------|
| Threshold | 10% day-over-day | Low enough to catch bulk imports, high enough to preserve real volatile days |
| Detection | First stable day wins | Simple, no multi-day confirmation needed — once imports stop, trading is real |
| Direction | Absolute value of % change | Both +15% and -15% swings are treated equally |
| Fallback | If no stable day found, keep all data | Avoids empty charts for edge cases |

---

## How

### Architecture

```
┌──────────────────────────┐
│ SQLite: daily_portfolio_  │
│ state table (db.py:106)  │
└──────────┬───────────────┘
           │ repository.get_daily_portfolio_states()
           ▼
┌──────────────────────────┐     ┌───────────────────────────┐
│ performance_view.py      │────▶│ benchmark_fetcher.py      │
│  • Aggregation (L26-35)  │     │  • yfinance + SQLite cache│
│  • Stabilization (L37-47)│     │  • S&P 500, TA-125       │
│  • Metrics (L74-84)      │     └───────────────────────────┘
│  • Charts (L94-150)      │
└──────────┬───────────────┘
           │ calls
           ▼
┌──────────────────────────┐
│ performance_metrics.py   │
│  • compute_cagr          │
│  • compute_max_drawdown  │
│  • compute_sharpe_ratio  │
│  • compute_cumulative_   │
│    returns               │
└──────────────────────────┘
```

### Data Flow

1. **Load** — `repository.get_daily_portfolio_states()` ([repository.py:217-224](src/database/repository.py#L217-L224)) queries `daily_portfolio_state` ordered by date
2. **Aggregate** — Each row's value = `total_cost_nis + cum_realized_pnl_nis + (cum_realized_pnl_usd × fx_rate)` ([performance_view.py:29-31](src/dashboard/views/performance_view.py#L29-L31))
3. **Filter** — Stabilization detection trims the leading build-up period ([performance_view.py:37-47](src/dashboard/views/performance_view.py#L37-L47))
4. **Inject** — Optional: append today's live market value as the final data point ([performance_view.py:49-55](src/dashboard/views/performance_view.py#L49-L55))
5. **Benchmark** — Fetch S&P 500 and TA-125 from Yahoo Finance with SQLite caching ([benchmark_fetcher.py:15-47](src/market/benchmark_fetcher.py#L15-L47))
6. **Compute** — Calculate Total Return, CAGR, Max Drawdown, Sharpe Ratio ([performance_metrics.py](src/dashboard/components/performance_metrics.py))
7. **Render** — Two Plotly charts + metric cards via Streamlit

### Stabilization Detection Algorithm

```python
# performance_view.py lines 37-47
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
| Total Return | `(end / start - 1) × 100` | [performance_view.py:75](src/dashboard/views/performance_view.py#L75) |
| CAGR | `(end / start)^(1/years) - 1` using 365.25 days/year | [performance_metrics.py:13-28](src/dashboard/components/performance_metrics.py#L13-L28) |
| Max Drawdown | `min((series - cummax) / cummax)` | [performance_metrics.py:31-37](src/dashboard/components/performance_metrics.py#L31-L37) |
| Sharpe Ratio | `mean(excess) / std(excess) × √252`, risk-free = 4% | [performance_metrics.py:40-57](src/dashboard/components/performance_metrics.py#L40-L57) |

### Benchmark Caching

Benchmark prices are cached in `benchmark_cache` table ([db.py:153-159](src/database/db.py#L153-L159)). The fetcher checks cached date ranges and only requests missing periods from yfinance, minimizing API calls.

---

## What

### Features

1. **4 Metric Cards** — Total Return, CAGR, Max Drawdown, Sharpe Ratio displayed in a row
2. **Benchmark Captions** — Total Return and CAGR for each benchmark shown below the cards
3. **Portfolio Value Chart** — Line chart of portfolio value (₪) over time
4. **Cumulative Returns Chart** — Base-100 normalized chart comparing portfolio vs benchmarks
5. **Auto Build-Up Detection** — Automatically skips initial import period (>10% daily swings)
6. **Live Value Injection** — Today's market value appended as the latest data point
7. **Benchmark Caching** — SQLite cache for S&P 500 and TA-125 prices

### Supported Benchmarks

| Name | Symbol | Style in Chart |
|------|--------|----------------|
| S&P 500 | `^GSPC` | Orange dashed |
| TA-125 | `TA125.TA` | Green dashed |

### Inputs

| Input | Source | Description |
|-------|--------|-------------|
| `daily_portfolio_state` rows | SQLite DB | Historical daily portfolio snapshots |
| `current_market_value_nis` | Passed from [app.py:199-215](app.py#L199-L215) | Live portfolio value for today's data point |
| Benchmark prices | Yahoo Finance / cache | S&P 500 and TA-125 closing prices |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| 4 metric cards | `st.metric` | Key performance indicators |
| Benchmark captions | `st.caption` | Per-benchmark Total Return + CAGR |
| Portfolio Value chart | Plotly `go.Scatter` | Value in ₪ over time (400px) |
| Cumulative Returns chart | Plotly `go.Scatter` | Base-100 multi-line comparison (450px) |
| Disclaimer caption | `st.caption` | Notes cost-basis methodology |

### Limitations

- Portfolio value is **cost basis + realized P&L only** — unrealized gains/losses on open positions are not reflected
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
