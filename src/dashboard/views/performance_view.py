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
    monthly_returns_bar,
    rolling_sharpe_chart,
)


def _stable_start_filter(series: pd.Series) -> pd.Series:
    """Drop leading data points where day-over-day change exceeds 10%."""
    series = series[series > 0]
    if series.empty:
        return series
    pct_change = series.pct_change().abs()
    stable_mask = pct_change <= 0.10
    if stable_mask.any():
        first_stable = stable_mask.idxmax()
        series = series.loc[first_stable:]
    return series


def render() -> None:
    """Render the Performance tab."""
    st.markdown(section_header("Portfolio Performance"), unsafe_allow_html=True)

    # ── Build portfolio value series ─────────────────────────────────────────
    states = repository.get_daily_portfolio_states()
    if not states:
        st.info("No daily portfolio data yet. Import transactions first.")
        return

    dates, values = [], []
    mv_dates, mv_values = [], []
    for row in states:
        value = (row["total_cost_nis"]
                 + row["cum_realized_pnl_nis"]
                 + row["cum_realized_pnl_usd"] * row["fx_rate"])
        dates.append(row["date"])
        values.append(value)

        mv = row["total_market_value_nis"]
        if mv and mv > 0:
            mv_dates.append(row["date"])
            mv_values.append(mv)

    portfolio_series = _stable_start_filter(
        pd.Series(values, index=pd.to_datetime(dates)))

    if len(portfolio_series) < 2:
        st.info("Not enough data points for performance analysis.")
        return

    # Market-value series (may be empty if no prices fetched yet)
    market_value_series = _stable_start_filter(
        pd.Series(mv_values, index=pd.to_datetime(mv_dates)))

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

    # ── Metric cards (prefer market value; fall back to book value) ─────────
    metrics_series = market_value_series if len(market_value_series) >= 2 else portfolio_series
    total_return = (metrics_series.iloc[-1] / metrics_series.iloc[0] - 1) * 100
    cagr = compute_cagr(metrics_series)
    max_dd = compute_max_drawdown(metrics_series)
    sharpe = compute_sharpe_ratio(metrics_series)

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

    # ── Chart 1: Invested Capital (Area with Gradient) ─────────────────────
    fig_value = area_chart_with_gradient(portfolio_series, "Invested Capital",
                                         theme.BM_PORTFOLIO)
    fig_value.update_layout(title="Invested Capital Over Time")
    st.plotly_chart(fig_value, use_container_width=True)

    # ── Chart 2: Drawdown (Underwater Plot) ──────────────────────────────────
    fig_dd = drawdown_chart(metrics_series)
    st.plotly_chart(fig_dd, use_container_width=True)

    # ── Benchmark line styles (shared by charts below) ───────────────────────
    bm_line_styles = {
        "S&P 500": dict(color=theme.BM_SP500, dash="dash"),
        "TA-125": dict(color=theme.BM_TA125, dash="dash"),
    }

    # ── Chart 3: Invested Capital vs Benchmarks ─────────────────────────────
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
        title="Invested Capital vs Benchmarks (base 100)",
        yaxis_title="Indexed Value",
        height=450,
        hovermode="x unified",
        margin=dict(t=40, b=20),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    # ── Chart 3b: Cumulative Returns vs Benchmarks (market value) ────────────
    if len(market_value_series) >= 2:
        mv_norm = compute_cumulative_returns(market_value_series)

        fig_ret = go.Figure()
        fig_ret.add_trace(go.Scatter(
            x=mv_norm.index, y=mv_norm.values,
            mode="lines", name="Portfolio",
            line=dict(color=theme.BM_PORTFOLIO, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0, 212, 170, 0.05)",
        ))

        for bm_name, bm_series in benchmarks.items():
            aligned = bm_series[bm_series.index >= market_value_series.index[0]]
            if aligned.empty:
                continue
            bm_norm = compute_cumulative_returns(aligned)
            style = bm_line_styles.get(bm_name, dict(color=theme.NEUTRAL, dash="dash"))
            fig_ret.add_trace(go.Scatter(
                x=bm_norm.index, y=bm_norm.values,
                mode="lines", name=bm_name,
                line=style,
            ))

        fig_ret.add_hline(y=100, line_dash="dot", line_color=theme.TEXT_MUTED, opacity=0.5)
        fig_ret.update_layout(
            title="Cumulative Returns vs Benchmarks (base 100)",
            yaxis_title="Indexed Value",
            height=450,
            hovermode="x unified",
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig_ret, use_container_width=True)

    # ── Chart 3c: Invested Capital — US vs TASE ─────────────────────────────
    us_dates, us_values, tase_dates, tase_values = [], [], [], []
    for row in states:
        us_val = (row["usd_total_cost"] + row["cum_realized_pnl_usd"]) * row["fx_rate"]
        tase_val = row["nis_total_cost"] + row["cum_realized_pnl_nis"]
        d = row["date"]
        if us_val > 0:
            us_dates.append(d)
            us_values.append(us_val)
        if tase_val > 0:
            tase_dates.append(d)
            tase_values.append(tase_val)

    us_series = pd.Series(us_values, index=pd.to_datetime(us_dates))
    tase_series = pd.Series(tase_values, index=pd.to_datetime(tase_dates))

    if len(us_series) >= 2 and len(tase_series) >= 2:
        common_start = max(us_series.index[0], tase_series.index[0])
        us_series = us_series.loc[common_start:]
        tase_series = tase_series.loc[common_start:]

        us_norm = compute_cumulative_returns(us_series)
        tase_norm = compute_cumulative_returns(tase_series)

        fig_split = go.Figure()
        fig_split.add_trace(go.Scatter(
            x=us_norm.index, y=us_norm.values,
            mode="lines", name="US Portfolio",
            line=dict(color=theme.BM_SP500, width=2.5),
        ))
        fig_split.add_trace(go.Scatter(
            x=tase_norm.index, y=tase_norm.values,
            mode="lines", name="TASE Portfolio",
            line=dict(color=theme.BM_TA125, width=2.5),
        ))
        fig_split.add_hline(y=100, line_dash="dot", line_color=theme.TEXT_MUTED, opacity=0.5)
        fig_split.update_layout(
            title="Invested Capital — US vs TASE (base 100)",
            yaxis_title="Indexed Value",
            height=450,
            hovermode="x unified",
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig_split, use_container_width=True)

    # ── Chart 3d: Cumulative Returns — US vs TASE (market value) ─────────────
    us_mv_dates, us_mv_values = [], []
    tase_mv_dates, tase_mv_values = [], []
    for row in states:
        d = row["date"]
        us_mv = row["usd_market_value"]
        tase_mv = row["nis_market_value"]
        us_cash = row["usd_cash"] or 0
        nis_cash_val = row["nis_cash"] or 0
        fx = row["fx_rate"] or 3.7
        if us_mv and us_mv > 0:
            us_mv_dates.append(d)
            us_mv_values.append((us_mv + us_cash) * fx)
        if tase_mv and tase_mv > 0:
            tase_mv_dates.append(d)
            tase_mv_values.append(tase_mv + nis_cash_val)

    us_mv_series = pd.Series(us_mv_values, index=pd.to_datetime(us_mv_dates))
    tase_mv_series = pd.Series(tase_mv_values, index=pd.to_datetime(tase_mv_dates))

    if len(us_mv_series) >= 2 and len(tase_mv_series) >= 2:
        common_start = max(us_mv_series.index[0], tase_mv_series.index[0])
        us_mv_series = us_mv_series.loc[common_start:]
        tase_mv_series = tase_mv_series.loc[common_start:]

        us_mv_norm = compute_cumulative_returns(us_mv_series)
        tase_mv_norm = compute_cumulative_returns(tase_mv_series)

        fig_ret_split = go.Figure()
        fig_ret_split.add_trace(go.Scatter(
            x=us_mv_norm.index, y=us_mv_norm.values,
            mode="lines", name="US Portfolio",
            line=dict(color=theme.BM_SP500, width=2.5),
        ))
        fig_ret_split.add_trace(go.Scatter(
            x=tase_mv_norm.index, y=tase_mv_norm.values,
            mode="lines", name="TASE Portfolio",
            line=dict(color=theme.BM_TA125, width=2.5),
        ))
        fig_ret_split.add_hline(y=100, line_dash="dot", line_color=theme.TEXT_MUTED, opacity=0.5)
        fig_ret_split.update_layout(
            title="Cumulative Returns — US vs TASE (base 100)",
            yaxis_title="Indexed Value",
            height=450,
            hovermode="x unified",
            margin=dict(t=40, b=20),
        )
        st.plotly_chart(fig_ret_split, use_container_width=True)

    # ── Chart 4 & 5: Monthly Returns + Rolling Sharpe (side by side) ────────
    col1, col2 = st.columns(2)

    with col1:
        fig_monthly = monthly_returns_bar(metrics_series)
        if fig_monthly:
            st.plotly_chart(fig_monthly, use_container_width=True)

    with col2:
        fig_sharpe = rolling_sharpe_chart(metrics_series)
        if fig_sharpe:
            st.plotly_chart(fig_sharpe, use_container_width=True)

    st.caption(
        "Invested Capital charts show cost basis + realized P&L. "
        "Cumulative Returns charts show actual market value including unrealized gains/losses."
    )
