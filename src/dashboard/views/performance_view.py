"""Tab — Portfolio Performance over time with benchmark comparison."""
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.database import repository
from src.market.benchmark_fetcher import BENCHMARKS, fetch_benchmark
from src.dashboard.components.performance_metrics import (
    compute_cagr,
    compute_cumulative_returns,
    compute_max_drawdown,
    compute_sharpe_ratio,
)


def render(current_market_value_nis: float | None = None) -> None:
    """Render the Performance tab."""
    # ── Build portfolio value series ─────────────────────────────────────────
    states = repository.get_daily_portfolio_states()
    if not states:
        st.info("No daily portfolio data yet. Import transactions first.")
        return

    dates = []
    values = []
    for row in states:
        value = (row["total_cost_nis"]
                 + row["cum_realized_pnl_nis"]
                 + row["cum_realized_pnl_usd"] * row["fx_rate"])
        dates.append(row["date"])
        values.append(value)

    portfolio_series = pd.Series(values, index=pd.to_datetime(dates))

    # Skip initial build-up: drop leading data points where day-over-day
    # change exceeds 10% (account migration / bulk import period).
    portfolio_series = portfolio_series[portfolio_series > 0]
    if portfolio_series.empty:
        st.info("Portfolio has no positive values to display.")
        return
    pct_change = portfolio_series.pct_change().abs()
    stable_mask = pct_change <= 0.10
    if stable_mask.any():
        first_stable = stable_mask.idxmax()  # first True
        portfolio_series = portfolio_series.loc[first_stable:]

    # Append current market value as today's data point
    if current_market_value_nis is not None and current_market_value_nis > 0:
        today = pd.Timestamp(date.today())
        if today not in portfolio_series.index:
            portfolio_series[today] = current_market_value_nis
        else:
            portfolio_series.loc[today] = current_market_value_nis

    if len(portfolio_series) < 2:
        st.info("Not enough data points for performance analysis.")
        return

    start_date = portfolio_series.index[0].strftime("%Y-%m-%d")
    end_date = portfolio_series.index[-1].strftime("%Y-%m-%d")

    # ── Fetch benchmarks ─────────────────────────────────────────────────────
    benchmarks: dict[str, pd.Series] = {}
    for bm_name in BENCHMARKS:
        bm_data = fetch_benchmark(bm_name, start_date, end_date)
        if bm_data:
            bm_series = pd.Series(bm_data)
            bm_series.index = pd.to_datetime(bm_series.index)
            bm_series = bm_series.sort_index()
            benchmarks[bm_name] = bm_series

    # ── Metric cards ─────────────────────────────────────────────────────────
    total_return = (portfolio_series.iloc[-1] / portfolio_series.iloc[0] - 1) * 100
    cagr = compute_cagr(portfolio_series)
    max_dd = compute_max_drawdown(portfolio_series)
    sharpe = compute_sharpe_ratio(portfolio_series)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Return", f"{total_return:+.1f}%")
    m2.metric("CAGR", f"{cagr:+.1f}%")
    m3.metric("Max Drawdown", f"{max_dd:.1f}%")
    m4.metric("Sharpe Ratio", f"{sharpe:.2f}")

    # ── Benchmark comparison captions ────────────────────────────────────────
    for bm_name, bm_series in benchmarks.items():
        bm_return = (bm_series.iloc[-1] / bm_series.iloc[0] - 1) * 100
        bm_cagr = compute_cagr(bm_series)
        st.caption(f"{bm_name}: Total Return **{bm_return:+.1f}%** | CAGR **{bm_cagr:+.1f}%**")

    st.divider()

    # ── Chart 1: Portfolio Value Over Time ───────────────────────────────────
    fig_value = go.Figure()
    fig_value.add_trace(go.Scatter(
        x=portfolio_series.index,
        y=portfolio_series.values,
        mode="lines",
        name="Portfolio Value",
        line=dict(color="#1f77b4", width=2),
    ))
    fig_value.update_layout(
        title="Portfolio Value Over Time",
        yaxis_title="Value (₪)",
        height=400,
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_value, use_container_width=True)

    # ── Chart 2: Cumulative Returns vs Benchmarks ────────────────────────────
    portfolio_norm = compute_cumulative_returns(portfolio_series)

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=portfolio_norm.index,
        y=portfolio_norm.values,
        mode="lines",
        name="Portfolio",
        line=dict(color="#1f77b4", width=2.5),
    ))

    bm_styles = {
        "S&P 500": dict(color="orange", dash="dash"),
        "TA-125": dict(color="green", dash="dash"),
    }
    for bm_name, bm_series in benchmarks.items():
        # Align to portfolio start date
        aligned = bm_series[bm_series.index >= portfolio_series.index[0]]
        if aligned.empty:
            continue
        bm_norm = compute_cumulative_returns(aligned)
        style = bm_styles.get(bm_name, dict(color="gray", dash="dash"))
        fig_cum.add_trace(go.Scatter(
            x=bm_norm.index,
            y=bm_norm.values,
            mode="lines",
            name=bm_name,
            line=style,
        ))

    fig_cum.add_hline(y=100, line_dash="dot", line_color="gray", opacity=0.5)
    fig_cum.update_layout(
        title="Cumulative Returns vs Benchmarks (base 100)",
        yaxis_title="Indexed Value",
        height=450,
        hovermode="x unified",
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    st.caption(
        "Portfolio value is based on cost basis + cumulative realized P&L. "
        "It does not reflect unrealized gains/losses on open positions."
    )
