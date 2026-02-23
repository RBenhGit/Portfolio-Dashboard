"""Statistics & Analytics tab for the Portfolio Dashboard."""

from __future__ import annotations

import datetime
from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.charts import _display_label
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
        st.warning("⚠️ Could not fetch USD/ILS rate. Using fallback 3.7.")

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
        rows.append(
            {
                "symbol": sym,
                "label": _display_label(sym, pos),
                "cost": cost,
                "value": value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "market": "NIS",
                "type": "stock",
            }
        )
        nis_stock_value += value

    for sym, pos in positions_usd.items():
        price = prices.get(sym)
        if price is None:
            continue
        cost = pos.total_invested_nis
        value = price * pos.quantity * fx
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost else 0.0
        rows.append(
            {
                "symbol": sym,
                "label": _display_label(sym, pos),
                "cost": cost,
                "value": value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "market": "USD",
                "type": "stock",
            }
        )
        usd_stock_value += value

    # --- Aggregates ---
    total_invested = sum(r["cost"] for r in rows)
    total_value = sum(r["value"] for r in rows)
    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0

    usd_cash_nis = usd_cash * fx
    total_cash = nis_cash + usd_cash_nis
    total_portfolio_value = total_value  # stocks only, matching merged view

    # Options: premiums from short options are already reflected in cash,
    # so we do NOT add options capital to portfolio value or allocation.

    # Count open options
    nis_options_open = sum(
        1 for pos in options_nis.values() if abs(pos.quantity) > 0.001
    )
    usd_options_open = sum(
        1 for pos in options_usd.values() if abs(pos.quantity) > 0.001
    )

    # =====================================================================
    # SECTION A — Portfolio Summary
    # =====================================================================
    st.subheader("Portfolio Summary")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Portfolio Value", f"₪{total_portfolio_value:,.0f}")
    c2.metric("Total P&L", f"₪{total_pnl:,.0f}")
    c3.metric("P&L %", f"{total_pnl_pct:+.1f}%")
    c4.metric("Total Cash", f"₪{total_cash:,.0f}")

    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("NIS Stocks", len(positions_nis))
    d2.metric("USD Stocks", len(positions_usd))
    d3.metric("NIS Options (open)", nis_options_open)
    d4.metric("USD Options (open)", usd_options_open)
    d5.metric(
        "Total Positions",
        len(positions_nis) + len(positions_usd) + nis_options_open + usd_options_open,
    )

    # Asset Allocation donut (stocks + cash only; option premiums are in cash)
    alloc_labels = ["NIS Stocks", "USD Stocks", "Cash"]
    alloc_values = [nis_stock_value, usd_stock_value, total_cash]

    if sum(alloc_values) > 0:
        fig_alloc = px.pie(
            names=alloc_labels,
            values=alloc_values,
            hole=0.45,
            title="Asset Allocation",
        )
        fig_alloc.update_traces(textinfo="percent+label")
        st.plotly_chart(fig_alloc, use_container_width=True, key="alloc_summary")

    # Top 5 Gainers / Losers
    if rows:
        sorted_rows = sorted(rows, key=lambda r: r["pnl_pct"], reverse=True)
        top_gainers = sorted_rows[:5]
        top_losers = sorted_rows[-5:][::-1]  # worst first

        col_g, col_l = st.columns(2)

        with col_g:
            st.markdown("**Top 5 Gainers**")
            g_data = [
                {
                    "Name": r["label"],
                    "P&L %": f"{r['pnl_pct']:+.1f}%",
                    "P&L ₪": f"₪{r['pnl']:,.0f}",
                }
                for r in top_gainers
                if r["pnl_pct"] > 0
            ]
            if g_data:
                st.table(g_data)
            else:
                st.info("No positions with gains.")

        with col_l:
            st.markdown("**Top 5 Losers**")
            l_data = [
                {
                    "Name": r["label"],
                    "P&L %": f"{r['pnl_pct']:+.1f}%",
                    "P&L ₪": f"₪{r['pnl']:,.0f}",
                }
                for r in top_losers
                if r["pnl_pct"] < 0
            ]
            if l_data:
                st.table(l_data)
            else:
                st.info("No positions with losses.")
    else:
        st.info("No stock positions to display.")

    # =====================================================================
    # SECTION B — Performance Metrics
    # =====================================================================
    st.divider()
    st.subheader("Performance Metrics")

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

        # Skip initial build-up period (daily change > 10%)
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

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Total Return", f"{total_return:+.1f}%")
            p2.metric("CAGR", f"{cagr:+.1f}%")
            p3.metric("Max Drawdown", f"{max_dd:.1f}%")
            p4.metric("Sharpe Ratio", f"{sharpe:.2f}")

            # Benchmark comparison captions
            start_d = port_series.index[0].strftime("%Y-%m-%d")
            end_d = port_series.index[-1].strftime("%Y-%m-%d")
            for bm_name in BENCHMARKS:
                bm_data = fetch_benchmark(bm_name, start_d, end_d)
                if bm_data:
                    bm_s = pd.Series(bm_data)
                    bm_s.index = pd.to_datetime(bm_s.index)
                    bm_s = bm_s.sort_index()
                    bm_ret = (bm_s.iloc[-1] / bm_s.iloc[0] - 1) * 100
                    bm_cagr = compute_cagr(bm_s)
                    st.caption(f"{bm_name}: Total Return **{bm_ret:+.1f}%** | CAGR **{bm_cagr:+.1f}%**")
        else:
            st.info("Not enough data points for performance metrics.")
    else:
        st.info("No daily portfolio data yet.")

    # =====================================================================
    # SECTION C — Trading Activity
    # =====================================================================
    st.divider()
    st.subheader("Trading Activity")

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

    # Average holding period
    avg_holding_days = None
    if realized_trades:
        holding_days_list = []
        # Build map of earliest buy date per symbol from transactions
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

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Total Trades", total_trades)
    e2.metric("Realized P&L", f"₪{total_realized_nis:,.0f}")
    e3.metric(
        "Win Rate",
        f"{win_rate:.0f}% ({wins}W/{losses}L)" if (wins + losses) > 0 else "N/A",
    )
    e4.metric(
        "Avg Holding Period",
        f"{avg_holding_days:.0f} days" if avg_holding_days is not None else "N/A",
    )

    # Most traded symbols
    if trade_txns:
        symbol_counts = Counter(
            t["security_symbol"] for t in trade_txns
        )
        top_traded = symbol_counts.most_common(5)
        symbols = [s for s, _ in top_traded]
        counts = [c for _, c in top_traded]

        fig_traded = go.Figure(
            go.Bar(
                x=counts,
                y=symbols,
                orientation="h",
                marker_color="#3498db",
            )
        )
        fig_traded.update_layout(
            title="Most Traded Symbols",
            xaxis_title="Number of Trades",
            yaxis=dict(autorange="reversed"),
            height=300,
        )
        st.plotly_chart(fig_traded, use_container_width=True)
    else:
        st.info("No trading activity recorded.")

    # =====================================================================
    # SECTION D — Risk & Diversification
    # =====================================================================
    st.divider()
    st.subheader("Risk & Diversification")

    total_stock_value = nis_stock_value + usd_stock_value
    nis_pct = (nis_stock_value / total_stock_value * 100) if total_stock_value else 0.0
    usd_pct = (usd_stock_value / total_stock_value * 100) if total_stock_value else 0.0

    # Largest position
    largest_label = "N/A"
    largest_pct = 0.0
    if rows and total_portfolio_value > 0:
        largest = max(rows, key=lambda r: r["value"])
        largest_label = largest["label"]
        largest_pct = largest["value"] / total_portfolio_value * 100

    total_stock_positions = len(positions_nis) + len(positions_usd)

    f1, f2, f3, f4 = st.columns(4)
    f1.metric("NIS Exposure", f"{nis_pct:.1f}%")
    f2.metric("USD Exposure", f"{usd_pct:.1f}%")
    f3.metric("Largest Position", f"{largest_label} ({largest_pct:.1f}%)")
    f4.metric("Total Stock Positions", total_stock_positions)

    col_pie1, col_pie2 = st.columns(2)

    with col_pie1:
        if sum(alloc_values) > 0:
            fig_alloc2 = px.pie(
                names=alloc_labels,
                values=alloc_values,
                hole=0.45,
                title="Asset Allocation",
            )
            fig_alloc2.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_alloc2, use_container_width=True, key="alloc_risk")

    with col_pie2:
        if total_stock_value > 0:
            fig_conc = px.pie(
                names=["NIS", "USD"],
                values=[nis_stock_value, usd_stock_value],
                hole=0.45,
                title="Market Concentration",
                color_discrete_sequence=["#3498db", "#e67e22"],
            )
            fig_conc.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_conc, use_container_width=True)
        else:
            st.info("No stock positions for market concentration analysis.")
