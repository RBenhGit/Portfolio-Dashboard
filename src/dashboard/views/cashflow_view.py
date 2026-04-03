"""Tab — Cash Flow analysis with cumulative, monthly, and category breakdowns."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import theme
from src.dashboard.styles import section_header, metric_card_html, html_table
from src.database import repository


_EFFECT_TO_CATEGORY = {
    "buy": "Stock Purchases",
    "sell": "Stock Sales",
    "dividend": "Dividends",
    "interest": "Interest",
    "fee": "Fees",
    "tax": "Taxes",
    "interest_tax": "Taxes",
    "forex_buy": "Forex Conversion",
    "forex_sell": "Forex Conversion",
}

_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=theme.TEXT_PRIMARY),
    hovermode="x unified",
    margin=dict(t=50, b=30, l=60, r=20),
)


def _build_cashflow_df() -> pd.DataFrame:
    """Fetch cash-flow transactions and return an enriched DataFrame."""
    rows = repository.get_cash_flow_transactions()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "date", "transaction_type", "effect", "security_name",
        "security_symbol", "market", "currency", "cash_flow_nis",
        "cash_flow_usd", "commission", "additional_fees",
    ])
    df["date"] = pd.to_datetime(df["date"])

    # FX rate lookup with forward-fill for missing dates
    fx_rates = repository.get_all_fx_rates()
    sorted_dates = sorted(fx_rates.keys())
    sorted_rates = [fx_rates[d] for d in sorted_dates]

    def _fx_for_date(dt: pd.Timestamp) -> float:
        date_str = dt.strftime("%Y-%m-%d")
        if date_str in fx_rates:
            return fx_rates[date_str]
        # Forward-fill: find the latest date <= dt
        for i in range(len(sorted_dates) - 1, -1, -1):
            if sorted_dates[i] <= date_str:
                return sorted_rates[i]
        return 3.7

    df["fx_rate"] = df["date"].apply(_fx_for_date)
    df["cash_flow_usd_as_nis"] = df["cash_flow_usd"] * df["fx_rate"]
    df["cash_flow_total_nis"] = df["cash_flow_nis"] + df["cash_flow_usd_as_nis"]

    def _categorize(row: pd.Series) -> str:
        effect = row["effect"]
        if effect in _EFFECT_TO_CATEGORY:
            return _EFFECT_TO_CATEGORY[effect]
        if effect == "transfer":
            return "Transfers In" if row["cash_flow_total_nis"] >= 0 else "Transfers Out"
        return "Other"

    df["category"] = df.apply(_categorize, axis=1)
    return df


def render(portfolio: dict) -> None:
    """Render the Cash Flow tab."""
    df = _build_cashflow_df()
    if df.empty:
        st.info("No cash flow data yet. Import transactions first.")
        return

    # ── Section 0 — Capital Allocation ──────────────────────────────────
    nis_cash = portfolio.get("nis_cash", 0.0)
    usd_cash = portfolio.get("usd_cash", 0.0)
    nis_invested = sum(
        p.total_invested for p in portfolio.get("positions_nis", {}).values()
    )
    usd_invested = sum(
        p.total_invested for p in portfolio.get("positions_usd", {}).values()
    )

    # Latest FX rate for NIS equivalents
    fx_rates = repository.get_all_fx_rates()
    latest_fx = list(fx_rates.values())[-1] if fx_rates else 3.7

    total_free_cash_nis = nis_cash + usd_cash * latest_fx
    total_invested_nis = nis_invested + usd_invested * latest_fx

    st.markdown(section_header("Capital Allocation"), unsafe_allow_html=True)

    a1, a2, a3 = st.columns(3)
    with a1:
        st.markdown(
            metric_card_html("Free Cash (NIS)", f"₪{nis_cash:,.0f}"),
            unsafe_allow_html=True)
    with a2:
        st.markdown(
            metric_card_html("Free Cash (USD)", f"${usd_cash:,.2f}"),
            unsafe_allow_html=True)
    with a3:
        st.markdown(
            metric_card_html("Total Free Cash", f"₪{total_free_cash_nis:,.0f}",
                             delta=f"${usd_cash:,.0f} × {latest_fx:.2f}"),
            unsafe_allow_html=True)

    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown(
            metric_card_html("Invested (NIS)", f"₪{nis_invested:,.0f}"),
            unsafe_allow_html=True)
    with b2:
        st.markdown(
            metric_card_html("Invested (USD)", f"${usd_invested:,.0f}"),
            unsafe_allow_html=True)
    with b3:
        st.markdown(
            metric_card_html("Total Invested", f"₪{total_invested_nis:,.0f}",
                             delta=f"${usd_invested:,.0f} × {latest_fx:.2f}"),
            unsafe_allow_html=True)

    st.divider()

    # ── Section 1 — Cash Flow Summary ───────────────────────────────────
    total_nis = df["cash_flow_total_nis"]

    st.markdown(section_header("Cash Flow Summary"), unsafe_allow_html=True)

    # External flows: deposits & withdrawals
    deposits = df.loc[
        (df["effect"] == "transfer") & (total_nis > 0), "cash_flow_total_nis"
    ].sum()
    withdrawals = df.loc[
        (df["effect"] == "transfer") & (total_nis < 0), "cash_flow_total_nis"
    ].sum()
    net_external = deposits + withdrawals

    r1c1, r1c2, r1c3 = st.columns(3)
    with r1c1:
        st.markdown(
            metric_card_html("Deposits", f"₪{deposits:,.0f}",
                             delta=f"+₪{deposits:,.0f}"),
            unsafe_allow_html=True)
    with r1c2:
        st.markdown(
            metric_card_html("Withdrawals", f"₪{abs(withdrawals):,.0f}",
                             delta=f"-₪{abs(withdrawals):,.0f}"),
            unsafe_allow_html=True)
    with r1c3:
        st.markdown(
            metric_card_html("Net External Flow", f"₪{net_external:,.0f}",
                             delta=f"{'+'if net_external >= 0 else ''}₪{net_external:,.0f}"),
            unsafe_allow_html=True)

    # Investment income
    total_dividends = df.loc[df["effect"] == "dividend", "cash_flow_total_nis"].sum()
    total_interest = df.loc[df["effect"] == "interest", "cash_flow_total_nis"].sum()
    fees_taxes_mask = df["effect"].isin(["fee", "tax", "interest_tax"])
    total_fees_taxes = df.loc[fees_taxes_mask, "cash_flow_total_nis"].sum()
    net_income = total_dividends + total_interest + total_fees_taxes

    r2c1, r2c2, r2c3 = st.columns(3)
    with r2c1:
        st.markdown(
            metric_card_html("Total Dividends", f"₪{total_dividends:,.0f}",
                             delta=f"+₪{total_dividends:,.0f}"),
            unsafe_allow_html=True)
    with r2c2:
        st.markdown(
            metric_card_html("Fees & Taxes", f"₪{abs(total_fees_taxes):,.0f}",
                             delta=f"-₪{abs(total_fees_taxes):,.0f}"),
            unsafe_allow_html=True)
    with r2c3:
        st.markdown(
            metric_card_html("Net Investment Income", f"₪{net_income:,.0f}",
                             delta=f"{'+'if net_income >= 0 else ''}₪{net_income:,.0f}"),
            unsafe_allow_html=True)

    st.divider()

    # ── Section 2 — Cumulative Cash Flow Over Time ──────────────────────
    daily = df.groupby("date")["cash_flow_total_nis"].sum().sort_index()
    daily_pos = daily.clip(lower=0)
    daily_neg = daily.clip(upper=0)
    cum_in = daily_pos.cumsum()
    cum_out = daily_neg.cumsum()
    cum_net = daily.cumsum()

    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=cum_in.index, y=cum_in.values,
        mode="lines", name="Cumulative Inflows",
        fill="tozeroy",
        line=dict(color=theme.PROFIT, width=1),
        fillcolor="rgba(16, 185, 129, 0.3)",
    ))
    fig_cum.add_trace(go.Scatter(
        x=cum_out.index, y=cum_out.values,
        mode="lines", name="Cumulative Outflows",
        fill="tozeroy",
        line=dict(color=theme.LOSS, width=1),
        fillcolor="rgba(239, 68, 68, 0.3)",
    ))
    fig_cum.add_trace(go.Scatter(
        x=cum_net.index, y=cum_net.values,
        mode="lines", name="Net Cumulative",
        line=dict(color=theme.ACCENT_PRIMARY, width=2.5),
    ))
    fig_cum.update_layout(
        **_CHART_LAYOUT,
        title="Cumulative Cash Flow Over Time",
        height=420,
        xaxis=dict(gridcolor=theme.BORDER_SUBTLE),
        yaxis=dict(gridcolor=theme.BORDER_SUBTLE),
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    # ── Section 3 — Monthly Cash Flow ───────────────────────────────────
    df_monthly = df.set_index("date").resample("ME")["cash_flow_total_nis"]
    monthly_pos = df_monthly.apply(lambda s: s[s > 0].sum())
    monthly_neg = df_monthly.apply(lambda s: s[s < 0].sum())
    monthly_net = df_monthly.sum()

    fig_monthly = go.Figure()
    fig_monthly.add_trace(go.Bar(
        x=monthly_pos.index, y=monthly_pos.values,
        name="Inflows", marker_color=theme.PROFIT,
    ))
    fig_monthly.add_trace(go.Bar(
        x=monthly_neg.index, y=monthly_neg.values,
        name="Outflows", marker_color=theme.LOSS,
    ))
    fig_monthly.add_trace(go.Scatter(
        x=monthly_net.index, y=monthly_net.values,
        mode="lines+markers", name="Net Flow",
        line=dict(color=theme.ACCENT_PRIMARY, width=2),
        marker=dict(size=4),
    ))
    fig_monthly.update_layout(
        **_CHART_LAYOUT,
        title="Monthly Cash Flow",
        height=400,
        barmode="relative",
        xaxis=dict(gridcolor=theme.BORDER_SUBTLE, tickformat="%b %Y"),
        yaxis=dict(gridcolor=theme.BORDER_SUBTLE),
    )
    st.plotly_chart(fig_monthly, use_container_width=True)

    # ── Section 4 — Breakdown by Category ───────────────────────────────
    cat_net = df.groupby("category")["cash_flow_total_nis"].sum().sort_values()
    cat_inflows = (
        df.loc[df["cash_flow_total_nis"] > 0]
        .groupby("category")["cash_flow_total_nis"]
        .sum()
        .sort_values(ascending=False)
    )

    col_bar, col_pie = st.columns(2)

    with col_bar:
        bar_colors = [theme.PROFIT if v >= 0 else theme.LOSS for v in cat_net.values]
        fig_cat_bar = go.Figure(go.Bar(
            x=cat_net.values,
            y=cat_net.index,
            orientation="h",
            marker_color=bar_colors,
            text=[f"₪{v:,.0f}" for v in cat_net.values],
            textposition="outside",
        ))
        fig_cat_bar.update_layout(
            **_CHART_LAYOUT,
            title="Net Flow by Category",
            height=400,
            xaxis=dict(gridcolor=theme.BORDER_SUBTLE),
            yaxis=dict(gridcolor=theme.BORDER_SUBTLE),
            showlegend=False,
        )
        st.plotly_chart(fig_cat_bar, use_container_width=True)

    with col_pie:
        if not cat_inflows.empty:
            n_colors = len(cat_inflows)
            pie_colors = (theme.CHART_COLORS * ((n_colors // len(theme.CHART_COLORS)) + 1))[:n_colors]
            fig_pie = go.Figure(go.Pie(
                labels=cat_inflows.index,
                values=cat_inflows.values,
                hole=0.35,
                marker=dict(colors=pie_colors),
                textinfo="percent+label",
            ))
            fig_pie.update_layout(
                **_CHART_LAYOUT,
                title="Inflow Composition",
                height=400,
                showlegend=False,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()

    # ── Section 5 — Yearly Summary Table ────────────────────────────────
    st.markdown(section_header("Yearly Summary"), unsafe_allow_html=True)

    df["year"] = df["date"].dt.year
    yearly = df.groupby("year").agg(
        cash_in=("cash_flow_total_nis", lambda s: s[s > 0].sum()),
        cash_out=("cash_flow_total_nis", lambda s: s[s < 0].sum()),
        net_flow=("cash_flow_total_nis", "sum"),
        dividends=("cash_flow_total_nis",
                    lambda s: s[df.loc[s.index, "effect"] == "dividend"].sum()),
        fees_taxes=("cash_flow_total_nis",
                     lambda s: s[df.loc[s.index, "effect"].isin(
                         ["fee", "tax", "interest_tax"])].sum()),
        n_transactions=("cash_flow_total_nis", "count"),
    )

    yr_headers = [
        "Year", "Cash In", "Cash Out", "Net Flow",
        "Dividends", "Fees & Taxes", "# Transactions",
    ]
    yr_rows = []
    for year, row in yearly.iterrows():
        net = row["net_flow"]
        net_fmt = f"₪{net:+,.0f}"
        pill_cls = "gain" if net >= 0 else "loss"
        yr_rows.append([
            str(year),
            f"₪{row['cash_in']:,.0f}",
            f"₪{abs(row['cash_out']):,.0f}",
            f'<span class="pnl-pill {pill_cls}">{net_fmt}</span>',
            f"₪{row['dividends']:,.0f}",
            f"₪{abs(row['fees_taxes']):,.0f}",
            f"{int(row['n_transactions']):,}",
        ])
    st.markdown(
        html_table(yr_headers, yr_rows, ["l", "r", "r", "r", "r", "r", "r"]),
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Section 6 — Transaction Details ─────────────────────────────────
    with st.expander("\U0001f4cb Transaction Details"):
        detail_df = df.sort_values("date", ascending=False).head(200)
        detail_headers = [
            "Date", "Type", "Security", "NIS Flow", "USD Flow", "Total (\u20aa)",
        ]
        detail_rows = []
        for _, r in detail_df.iterrows():
            nis_val = r["cash_flow_nis"]
            usd_val = r["cash_flow_usd"]
            total_val = r["cash_flow_total_nis"]

            def _pill(v: float) -> str:
                cls = "gain" if v >= 0 else "loss"
                return f'<span class="pnl-pill {cls}">₪{v:+,.0f}</span>'

            def _flow_fmt(v: float, sym: str = "₪") -> str:
                cls = "gain" if v >= 0 else "loss"
                return f'<span class="pnl-pill {cls}">{sym}{v:+,.2f}</span>'

            sec_name = r["security_name"] or ""
            detail_rows.append([
                r["date"].strftime("%Y-%m-%d"),
                r["transaction_type"] or r["effect"],
                sec_name,
                _flow_fmt(nis_val, "₪"),
                _flow_fmt(usd_val, "$"),
                _pill(total_val),
            ])
        st.markdown(
            html_table(detail_headers, detail_rows, ["l", "l", "l", "r", "r", "r"]),
            unsafe_allow_html=True,
        )
