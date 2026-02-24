"""Statistics & Analytics tab for the Portfolio Dashboard."""

from __future__ import annotations

import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import theme
from src.dashboard.styles import section_header, metric_card_html, html_table
from src.dashboard.components.charts import (
    _display_label, allocation_treemap,
)
from src.dashboard.components.performance_metrics import (
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe_ratio,
)
from src.database import repository
from src.market.benchmark_fetcher import BENCHMARKS, fetch_benchmark


def render(portfolio: dict, prices: dict, price_date: str = "") -> None:
    """Render the Statistics & Analytics tab."""

    # --- FX resolution ---
    fx = repository.get_fx_rate(price_date) if price_date else None
    if fx is None:
        from src.market.fx_fetcher import get_current_fx_rate
        fx = get_current_fx_rate()
    if fx is None:
        fx = 3.7
        st.warning("Could not fetch USD/ILS rate. Using fallback 3.7.")

    # --- Extract positions ---
    positions_nis = portfolio.get("positions_nis", {})
    positions_usd = portfolio.get("positions_usd", {})
    options_nis = portfolio.get("options_nis", {})
    options_usd = portfolio.get("options_usd", {})
    nis_cash = portfolio.get("nis_cash", 0.0)
    usd_cash = portfolio.get("usd_cash", 0.0)

    # --- Build unified rows in NIS ---
    rows = []
    nis_stock_value = 0.0
    usd_stock_value = 0.0

    for sym, pos in positions_nis.items():
        price = prices.get(sym)
        if price is None:
            continue
        cost = pos.total_invested
        value = price * pos.quantity
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost else 0.0
        rows.append({
            "symbol": sym, "label": _display_label(sym, pos),
            "cost": cost, "value": value, "pnl": pnl,
            "pnl_pct": pnl_pct, "market": "NIS", "type": "stock",
        })
        nis_stock_value += value

    for sym, pos in positions_usd.items():
        price = prices.get(sym)
        if price is None:
            continue
        cost = pos.total_invested_nis
        value = price * pos.quantity * fx
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost else 0.0
        rows.append({
            "symbol": sym, "label": _display_label(sym, pos),
            "cost": cost, "value": value, "pnl": pnl,
            "pnl_pct": pnl_pct, "market": "USD", "type": "stock",
        })
        usd_stock_value += value

    # --- Aggregates ---
    total_invested = sum(r["cost"] for r in rows)
    total_value = sum(r["value"] for r in rows)
    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0

    usd_cash_nis = usd_cash * fx
    total_cash = nis_cash + usd_cash_nis
    total_portfolio_value = total_value

    nis_options_open = sum(
        1 for pos in options_nis.values() if abs(pos.quantity) > 0.001
    )
    usd_options_open = sum(
        1 for pos in options_usd.values() if abs(pos.quantity) > 0.001
    )

    alloc_labels = ["NIS Stocks", "USD Stocks", "Cash"]
    alloc_values = [nis_stock_value, usd_stock_value, total_cash]
    total_stock_value = nis_stock_value + usd_stock_value
    nis_pct = (nis_stock_value / total_stock_value * 100) if total_stock_value else 0.0
    usd_pct = (usd_stock_value / total_stock_value * 100) if total_stock_value else 0.0

    # =====================================================================
    # TWO-COLUMN LAYOUT: Stats (left) | Charts (right)
    # =====================================================================
    col_stats, col_charts = st.columns([2, 3])

    # -----------------------------------------------------------------
    # LEFT COLUMN — All statistics / metrics / tables
    # -----------------------------------------------------------------
    with col_stats:
        # --- Portfolio Summary ---
        st.markdown(section_header("Portfolio Summary"), unsafe_allow_html=True)
        s1, s2 = st.columns(2)
        with s1:
            st.markdown(metric_card_html("Total Portfolio Value",
                                         f"₪{total_portfolio_value:,.0f}"),
                        unsafe_allow_html=True)
        with s2:
            pnl_delta = f"₪{total_pnl:+,.0f}"
            st.markdown(metric_card_html("Total P&L", f"₪{total_pnl:,.0f}",
                                         delta=pnl_delta),
                        unsafe_allow_html=True)
        s3, s4 = st.columns(2)
        with s3:
            st.markdown(metric_card_html("P&L %", f"{total_pnl_pct:+.1f}%",
                                         delta=f"{total_pnl_pct:+.1f}%"),
                        unsafe_allow_html=True)
        with s4:
            st.markdown(metric_card_html("Total Cash", f"₪{total_cash:,.0f}"),
                        unsafe_allow_html=True)

        # Position counts
        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
        d1, d2, d3 = st.columns(3)
        d1.metric("NIS Stocks", len(positions_nis))
        d2.metric("USD Stocks", len(positions_usd))
        d3.metric("Options (open)", nis_options_open + usd_options_open)

        # --- Performance Metrics ---
        st.markdown(section_header("Performance Metrics"), unsafe_allow_html=True)

        states = repository.get_daily_portfolio_states()
        if states:
            dates_perf = []
            values_perf = []
            for row in states:
                v = (row["total_cost_nis"]
                     + row["cum_realized_pnl_nis"]
                     + row["cum_realized_pnl_usd"] * row["fx_rate"])
                dates_perf.append(row["date"])
                values_perf.append(v)

            port_series = pd.Series(values_perf, index=pd.to_datetime(dates_perf))
            port_series = port_series[port_series > 0]

            if not port_series.empty:
                pct_chg = port_series.pct_change().abs()
                stable = pct_chg <= 0.10
                if stable.any():
                    port_series = port_series.loc[stable.idxmax():]

            if len(port_series) >= 2:
                total_return = (port_series.iloc[-1] / port_series.iloc[0] - 1) * 100
                cagr = compute_cagr(port_series)
                max_dd = compute_max_drawdown(port_series)
                sharpe = compute_sharpe_ratio(port_series)

                p1, p2 = st.columns(2)
                p1.metric("Total Return", f"{total_return:+.1f}%")
                p2.metric("CAGR", f"{cagr:+.1f}%")
                p3, p4 = st.columns(2)
                p3.metric("Max Drawdown", f"{max_dd:.1f}%")
                p4.metric("Sharpe Ratio", f"{sharpe:.2f}")

                start_d = port_series.index[0].strftime("%Y-%m-%d")
                end_d = port_series.index[-1].strftime("%Y-%m-%d")
                bm_colors = {"S&P 500": theme.BM_SP500, "TA-125": theme.BM_TA125}
                for bm_name in BENCHMARKS:
                    bm_data = fetch_benchmark(bm_name, start_d, end_d)
                    if bm_data:
                        bm_s = pd.Series(bm_data)
                        bm_s.index = pd.to_datetime(bm_s.index)
                        bm_s = bm_s.sort_index()
                        bm_ret = (bm_s.iloc[-1] / bm_s.iloc[0] - 1) * 100
                        bm_cagr = compute_cagr(bm_s)
                        bm_color = bm_colors.get(bm_name, theme.TEXT_SECONDARY)
                        st.markdown(
                            f'<span style="color:{bm_color};font-weight:600;">'
                            f'{bm_name}</span>'
                            f' Return: <b>{bm_ret:+.1f}%</b>'
                            f' | CAGR: <b>{bm_cagr:+.1f}%</b>',
                            unsafe_allow_html=True)
            else:
                st.info("Not enough data for performance metrics.")
        else:
            st.info("No daily portfolio data yet.")

        # --- Trading Activity ---
        st.markdown(section_header("Trading Activity"), unsafe_allow_html=True)

        realized_trades = repository.get_realized_trades()
        all_transactions = repository.get_all_transactions()
        trade_txns = [
            t for t in all_transactions if t["effect"] in ("buy", "sell")
        ]
        total_trades = len(trade_txns)

        cum_realized_nis = portfolio.get("cum_realized_pnl_nis", 0.0)
        cum_realized_usd = portfolio.get("cum_realized_pnl_usd", 0.0)
        total_realized_nis = cum_realized_nis + cum_realized_usd * fx

        wins = sum(1 for rt in realized_trades if rt["realized_pnl"] > 0)
        losses = sum(1 for rt in realized_trades if rt["realized_pnl"] < 0)
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

        avg_holding_days = None
        if realized_trades:
            holding_days_list = []
            earliest_buy: dict[str, datetime.date] = {}
            for t in all_transactions:
                if t["effect"] == "buy":
                    sym = t["security_symbol"]
                    tdate = t["date"]
                    if sym and tdate:
                        if isinstance(tdate, str):
                            tdate = datetime.date.fromisoformat(tdate)
                        if sym not in earliest_buy or tdate < earliest_buy[sym]:
                            earliest_buy[sym] = tdate

            for rt in realized_trades:
                sym = rt["security_symbol"]
                sell_date = rt["date"]
                if sym and sell_date and sym in earliest_buy:
                    if isinstance(sell_date, str):
                        sell_date = datetime.date.fromisoformat(sell_date)
                    days = (sell_date - earliest_buy[sym]).days
                    if days >= 0:
                        holding_days_list.append(days)

            if holding_days_list:
                avg_holding_days = sum(holding_days_list) / len(holding_days_list)

        e1, e2 = st.columns(2)
        e1.metric("Total Trades", total_trades)
        e2.metric("Realized P&L", f"₪{total_realized_nis:,.0f}")
        e3, e4 = st.columns(2)
        e3.metric(
            "Win Rate",
            f"{win_rate:.0f}% ({wins}W/{losses}L)" if (wins + losses) > 0 else "N/A",
        )
        e4.metric(
            "Avg Holding",
            f"{avg_holding_days:.0f}d" if avg_holding_days is not None else "N/A",
        )

        # --- Risk & Diversification ---
        st.markdown(section_header("Risk & Diversification"), unsafe_allow_html=True)

        largest_label = "N/A"
        largest_pct = 0.0
        if rows and total_portfolio_value > 0:
            largest = max(rows, key=lambda r: r["value"])
            largest_label = largest["label"]
            largest_pct = largest["value"] / total_portfolio_value * 100

        f1, f2 = st.columns(2)
        f1.metric("NIS Exposure", f"{nis_pct:.1f}%")
        f2.metric("USD Exposure", f"{usd_pct:.1f}%")
        st.metric("Largest Position", f"{largest_label} ({largest_pct:.1f}%)")

        # --- Top Gainers / Losers (side by side) ---
        if rows:
            sorted_rows = sorted(rows, key=lambda r: r["pnl_pct"], reverse=True)
            top_gainers = [r for r in sorted_rows[:5] if r["pnl_pct"] > 0]
            top_losers = [r for r in sorted_rows[-5:][::-1] if r["pnl_pct"] < 0]

            col_g, col_l = st.columns(2)
            with col_g:
                st.markdown(
                    f'<div style="color:{theme.PROFIT};font-weight:600;'
                    f'margin-bottom:4px;margin-top:8px;">Top Gainers</div>',
                    unsafe_allow_html=True)
                if top_gainers:
                    g_headers = ["Name", "P&L %"]
                    g_rows = [
                        [r["label"],
                         f'<span class="pnl-pill gain">{r["pnl_pct"]:+.1f}%</span>']
                        for r in top_gainers
                    ]
                    st.markdown(html_table(g_headers, g_rows, ["l", "r"]),
                                unsafe_allow_html=True)
                else:
                    st.info("No gains.")
            with col_l:
                st.markdown(
                    f'<div style="color:{theme.LOSS};font-weight:600;'
                    f'margin-bottom:4px;margin-top:8px;">Top Losers</div>',
                    unsafe_allow_html=True)
                if top_losers:
                    l_headers = ["Name", "P&L %"]
                    l_rows = [
                        [r["label"],
                         f'<span class="pnl-pill loss">{r["pnl_pct"]:+.1f}%</span>']
                        for r in top_losers
                    ]
                    st.markdown(html_table(l_headers, l_rows, ["l", "r"]),
                                unsafe_allow_html=True)
                else:
                    st.info("No losses.")

    # -----------------------------------------------------------------
    # RIGHT COLUMN — All charts / graphs
    # -----------------------------------------------------------------
    with col_charts:
        # --- Asset Allocation ---
        st.markdown(section_header("Asset Allocation"), unsafe_allow_html=True)

        if sum(alloc_values) > 0:
            chart_type = st.radio("Allocation view", ["Donut", "Treemap"],
                                  horizontal=True, key="stats_alloc_type")
            if chart_type == "Treemap":
                all_positions = {**positions_nis, **positions_usd}
                fig_alloc = allocation_treemap(all_positions, prices, "₪",
                                              "Portfolio Composition",
                                              fx_rate=fx)
                if fig_alloc:
                    fig_alloc.update_layout(height=280)
                    st.plotly_chart(fig_alloc, use_container_width=True,
                                    key="alloc_treemap")
            else:
                fig_alloc = px.pie(
                    names=alloc_labels, values=alloc_values,
                    hole=0.45, title="Asset Allocation",
                    color_discrete_sequence=theme.CHART_COLORS,
                )
                fig_alloc.update_traces(textinfo="percent+label")
                fig_alloc.update_layout(height=300)
                st.plotly_chart(fig_alloc, use_container_width=True,
                                key="alloc_summary")

        # --- P&L Breakdown bar chart (all in ₪, colored by market) ---
        if rows:
            pnl_rows = [r for r in rows if r["pnl"] != 0]
            pnl_rows.sort(key=lambda r: r["pnl"])
            tase = [r for r in pnl_rows if r["market"] == "NIS"]
            us = [r for r in pnl_rows if r["market"] == "USD"]

            fig_pnl = go.Figure()
            if tase:
                fig_pnl.add_trace(go.Bar(
                    x=[r["pnl"] for r in tase],
                    y=[r["label"] for r in tase],
                    orientation="h", name="TASE",
                    marker_color=theme.ACCENT_PRIMARY,
                    text=[f"₪{r['pnl']:+,.0f}" for r in tase],
                    textposition="outside",
                ))
            if us:
                fig_pnl.add_trace(go.Bar(
                    x=[r["pnl"] for r in us],
                    y=[r["label"] for r in us],
                    orientation="h", name="US",
                    marker_color=theme.BM_SP500,
                    text=[f"₪{r['pnl']:+,.0f}" for r in us],
                    textposition="outside",
                ))
            if tase or us:
                fig_pnl.update_layout(
                    title="P&L Breakdown (₪)",
                    height=max(280, len(pnl_rows) * 24 + 80),
                    margin=dict(t=50, b=20, l=80),
                    yaxis=dict(autorange="reversed"),
                    barmode="relative",
                    legend=dict(orientation="h", y=1.02, yanchor="bottom"),
                )
                st.plotly_chart(fig_pnl, use_container_width=True)

        # --- Currency Exposure (tabulated) ---
        st.markdown(section_header("Currency Exposure"), unsafe_allow_html=True)
        if total_stock_value > 0:
            exp_headers = ["Currency", "Value ₪", "Weight"]
            exp_rows = [
                [f'<span style="color:{theme.ACCENT_PRIMARY};font-weight:600;">NIS</span>',
                 f"₪{nis_stock_value:,.0f}",
                 f"{nis_pct:.1f}%"],
                [f'<span style="color:{theme.BM_SP500};font-weight:600;">USD</span>',
                 f"₪{usd_stock_value:,.0f}",
                 f"{usd_pct:.1f}%"],
            ]
            st.markdown(html_table(exp_headers, exp_rows, ["l", "r", "r"]),
                        unsafe_allow_html=True)
        else:
            st.info("No stock positions.")
