"""Tab 3 — Merged portfolio (all in ₪ using historical FX for cost, current for value)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.database import repository
from src.dashboard.components.charts import _display_label


def render(portfolio: dict, prices: dict, price_date: str = "") -> None:
    """Render merged tab: all positions unified in ₪.

    USD position cost = total_invested_nis (weighted historical FX).
    USD position value = quantity × price_on_date × fx_on_date.
    """
    positions_nis = portfolio.get("positions_nis", {})
    positions_usd = portfolio.get("positions_usd", {})
    nis_cash = portfolio.get("nis_cash", 0.0)
    usd_cash = portfolio.get("usd_cash", 0.0)

    # FX rate for the reference date
    fx = repository.get_fx_rate(price_date) if price_date else None
    if fx is None:
        from src.market.fx_fetcher import get_current_fx_rate
        fx = get_current_fx_rate()
    if fx is None:
        fx = 3.7
        st.warning("⚠️ Could not fetch USD/ILS rate. Using fallback 3.7.")

    st.caption(f"USD/ILS: **{fx:.4f}** (as of {price_date})" if price_date else f"USD/ILS: **{fx:.4f}**")

    # ── Build unified table ────────────────────────────────────────────────────
    rows = []

    for sym, pos in positions_nis.items():
        price = prices.get(sym)
        cost_nis = pos.total_invested          # already in ₪
        value_nis = (price * pos.quantity) if price else None
        pnl = (value_nis - cost_nis) if value_nis is not None else None
        pnl_pct = (pnl / cost_nis * 100) if (pnl is not None and cost_nis > 0) else None
        rows.append({
            "Symbol": sym, "Name": pos.security_name or "—",
            "Display": _display_label(sym, pos),
            "Mkt": pos.market, "Qty": pos.quantity,
            "Cost ₪": cost_nis, "Price ₪": price,
            "Value ₪": value_nis, "P&L ₪": pnl, "P&L %": pnl_pct,
        })

    for sym, pos in positions_usd.items():
        price_usd = prices.get(sym)
        cost_nis = pos.total_invested_nis      # historical FX baked in
        value_nis = (price_usd * pos.quantity * fx) if price_usd else None
        price_nis = (price_usd * fx) if price_usd else None
        pnl = (value_nis - cost_nis) if value_nis is not None else None
        pnl_pct = (pnl / cost_nis * 100) if (pnl is not None and cost_nis > 0) else None
        rows.append({
            "Symbol": sym, "Name": pos.security_name or "—",
            "Display": _display_label(sym, pos),
            "Mkt": pos.market, "Qty": pos.quantity,
            "Cost ₪": cost_nis, "Price ₪": price_nis,
            "Value ₪": value_nis, "P&L ₪": pnl, "P&L %": pnl_pct,
        })

    # ── Summary metrics ────────────────────────────────────────────────────────
    total_invested = sum(r["Cost ₪"] for r in rows if r["Cost ₪"])
    total_value    = sum(r["Value ₪"] for r in rows if r["Value ₪"] is not None)
    total_pnl      = total_value - total_invested
    total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    nis_cash_display = nis_cash
    usd_cash_nis     = usd_cash * fx
    total_cash_nis   = nis_cash_display + usd_cash_nis

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Invested ₪", f"₪{total_invested:,.0f}")
    m2.metric("Market Value ₪",   f"₪{total_value:,.0f}")
    m3.metric("Total P&L ₪",      f"₪{total_pnl:+,.0f}")
    m4.metric("P&L %",            f"{total_pnl_pct:+.1f}%")

    c1, c2, c3 = st.columns(3)
    c1.info(f"NIS Cash: **₪{nis_cash_display:,.2f}**")
    c2.info(f"USD Cash: **${usd_cash:,.2f}** = ₪{usd_cash_nis:,.2f}")
    c3.info(f"Total Cash: **₪{total_cash_nis:,.2f}**")

    st.divider()

    # ── Position table ─────────────────────────────────────────────────────────
    if not rows:
        st.info("No open positions.")
        return

    df = pd.DataFrame(rows)

    def _style_pnl(row):
        styles = [""] * len(row)
        if "P&L ₪" in row.index and pd.notna(row["P&L ₪"]):
            color = "#2ecc71" if row["P&L ₪"] >= 0 else "#e74c3c"
            for col in ("P&L ₪", "P&L %"):
                if col in row.index:
                    styles[list(row.index).index(col)] = f"color: {color}; font-weight: bold"
        return styles

    fmt = {
        "Qty":    "{:,.4f}",
        "Cost ₪": "₪{:,.2f}",
        "Price ₪":"₪{:,.2f}",
        "Value ₪":"₪{:,.2f}",
        "P&L ₪":  "₪{:+,.2f}",
        "P&L %":  "{:+.2f}%",
    }
    table_cols = [c for c in df.columns if c != "Display"]
    st.dataframe(
        df[table_cols].style.apply(_style_pnl, axis=1).format(fmt, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )

    # ── Charts ─────────────────────────────────────────────────────────────────
    valid = df[df["Value ₪"].notna() & (df["Value ₪"] > 0)]
    if not valid.empty:
        fig_pie = px.pie(
            valid, names="Display", values="Value ₪",
            title="Full Portfolio Allocation (₪)", hole=0.35,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(height=420, margin=dict(t=50, b=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    pnl_valid = df[df["P&L ₪"].notna()].sort_values("P&L ₪")
    if not pnl_valid.empty:
        fig_bar = go.Figure(go.Bar(
            x=pnl_valid["P&L ₪"],
            y=pnl_valid["Display"],
            orientation="h",
            marker_color=["#2ecc71" if v >= 0 else "#e74c3c" for v in pnl_valid["P&L ₪"]],
            text=[f"₪{v:+,.0f}" for v in pnl_valid["P&L ₪"]],
            textposition="outside",
        ))
        fig_bar.update_layout(
            title="P&L per Position (₪)",
            height=max(300, len(pnl_valid) * 28 + 80),
            margin=dict(t=40, b=20, l=80),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)
