"""Tab — Portfolio Performance over time with benchmark comparison."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import theme
from src.dashboard.styles import section_header
from src.database import repository
from src.market.benchmark_fetcher import BENCHMARKS, fetch_benchmark
from src.dashboard.components.performance_metrics import (
    compute_cagr,
    compute_cumulative_returns,
    compute_max_drawdown,
    compute_sharpe_ratio,
)
from src.dashboard.components.charts import (
    area_chart_with_gradient,
    drawdown_chart,
    monthly_returns_heatmap,
    monthly_returns_bar,
    rolling_sharpe_chart,
)


def render() -> None:
    """Render the Performance tab."""
    st.markdown(section_header("Portfolio Performance"), unsafe_allow_html=True)

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
        first_stable = stable_mask.idxmax()
        portfolio_series = portfolio_series.loc[first_stable:]

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

    # ── Benchmark comparison with colored labels ─────────────────────────────
    bm_colors = {"S&P 500": theme.BM_SP500, "TA-125": theme.BM_TA125}
    for bm_name, bm_series in benchmarks.items():
        bm_return = (bm_series.iloc[-1] / bm_series.iloc[0] - 1) * 100
        bm_cagr = compute_cagr(bm_series)
        bm_color = bm_colors.get(bm_name, theme.TEXT_SECONDARY)
        st.markdown(
            f'<span style="color:{bm_color};font-weight:600;">{bm_name}</span>'
            f' Total Return: <b>{bm_return:+.1f}%</b> | CAGR: <b>{bm_cagr:+.1f}%</b>',
            unsafe_allow_html=True)

    st.divider()

    # ── Chart 1: Portfolio Value (Area with Gradient) ────────────────────────
    fig_value = area_chart_with_gradient(portfolio_series, "Portfolio Value",
                                         theme.BM_PORTFOLIO)
    fig_value.update_layout(title="Portfolio Value Over Time")
    st.plotly_chart(fig_value, use_container_width=True)

    # ── Chart 2: Drawdown (Underwater Plot) ──────────────────────────────────
    fig_dd = drawdown_chart(portfolio_series)
    st.plotly_chart(fig_dd, use_container_width=True)

    # ── Chart 3: Cumulative Returns vs Benchmarks ────────────────────────────
    portfolio_norm = compute_cumulative_returns(portfolio_series)

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=portfolio_norm.index,
        y=portfolio_norm.values,
        mode="lines",
        name="Portfolio",
        line=dict(color=theme.BM_PORTFOLIO, width=2.5),
        fill="tozeroy",
        fillcolor="rgba(0, 212, 170, 0.05)",
    ))

    bm_line_styles = {
        "S&P 500": dict(color=theme.BM_SP500, dash="dash"),
        "TA-125": dict(color=theme.BM_TA125, dash="dash"),
    }
    for bm_name, bm_series in benchmarks.items():
        aligned = bm_series[bm_series.index >= portfolio_series.index[0]]
        if aligned.empty:
            continue
        bm_norm = compute_cumulative_returns(aligned)
        style = bm_line_styles.get(bm_name, dict(color=theme.NEUTRAL, dash="dash"))
        fig_cum.add_trace(go.Scatter(
            x=bm_norm.index,
            y=bm_norm.values,
            mode="lines",
            name=bm_name,
            line=style,
        ))

    fig_cum.add_hline(y=100, line_dash="dot", line_color=theme.TEXT_MUTED, opacity=0.5)
    fig_cum.update_layout(
        title="Cumulative Returns vs Benchmarks (base 100)",
        yaxis_title="Indexed Value",
        height=450,
        hovermode="x unified",
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    # ── Chart 4 & 5: Monthly Returns + Rolling Sharpe (side by side) ────────
    col1, col2 = st.columns(2)

    with col1:
        fig_monthly = monthly_returns_bar(portfolio_series)
        if fig_monthly:
            st.plotly_chart(fig_monthly, use_container_width=True)

    with col2:
        fig_sharpe = rolling_sharpe_chart(portfolio_series)
        if fig_sharpe:
            st.plotly_chart(fig_sharpe, use_container_width=True)

    # ── Chart 6: Monthly Returns Heatmap ─────────────────────────────────────
    fig_heatmap = monthly_returns_heatmap(portfolio_series)
    if fig_heatmap:
        st.plotly_chart(fig_heatmap, use_container_width=True)

    st.caption(
        "Portfolio value is based on cost basis + cumulative realized P&L. "
        "It does not reflect unrealized gains/losses on open positions."
    )
