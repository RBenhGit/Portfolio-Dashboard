"""Tab — Merged portfolio (all in ₪ using historical FX for cost, current for value)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import theme
from src.dashboard.styles import section_header, html_table
from src.dashboard.components.charts import _display_label
from src.database import repository


def render(portfolio: dict, prices: dict, price_date: str = "") -> None:
    """Render merged tab: all positions unified in ₪."""
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
        st.warning("Could not fetch USD/ILS rate. Using fallback 3.7.")

    st.markdown(section_header("Merged Portfolio (NIS)"), unsafe_allow_html=True)
    st.caption(f"USD/ILS: **{fx:.4f}**" + (f" (as of {price_date})" if price_date else ""))

    # ── Build unified table ──────────────────────────────────────────────────
    rows = []
    for sym, pos in positions_nis.items():
        price = prices.get(sym)
        cost_nis = pos.total_invested
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
        cost_nis = pos.total_invested_nis
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

    # ── Summary metrics ──────────────────────────────────────────────────────
    total_invested = sum(r["Cost ₪"] for r in rows if r["Cost ₪"])
    total_value = sum(r["Value ₪"] for r in rows if r["Value ₪"] is not None)
    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    usd_cash_nis = usd_cash * fx
    total_cash_nis = nis_cash + usd_cash_nis

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Invested ₪", f"₪{total_invested:,.0f}")
    m2.metric("Market Value ₪", f"₪{total_value:,.0f}")
    m3.metric("Total P&L ₪", f"₪{total_pnl:+,.0f}")
    m4.metric("P&L %", f"{total_pnl_pct:+.1f}%")

    # Cash cards
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="cash-card"><div class="label">NIS Cash</div>'
                    f'<div class="value">₪{nis_cash:,.2f}</div></div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="cash-card"><div class="label">USD Cash</div>'
                    f'<div class="value">${usd_cash:,.2f} = ₪{usd_cash_nis:,.2f}</div></div>',
                    unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="cash-card"><div class="label">Total Cash</div>'
                    f'<div class="value">₪{total_cash_nis:,.2f}</div></div>',
                    unsafe_allow_html=True)

    st.divider()

    # ── Position data ──────────────────────────────────────────────────────
    if not rows:
        st.info("No open positions.")
        return

    df = pd.DataFrame(rows)

    # ── Charts — allocation (donut) left, P&L right ──────────────────────
    col_alloc, col_pnl = st.columns([1, 2])

    with col_alloc:
        valid = df[df["Value ₪"].notna() & (df["Value ₪"] > 0)]
        if not valid.empty:
            fig_pie = px.pie(
                valid, names="Display", values="Value ₪",
                title="Full Portfolio Allocation (₪)", hole=0.35,
                color_discrete_sequence=theme.CHART_COLORS,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(height=420, margin=dict(t=50, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_pnl:
        pnl_valid = df[df["P&L ₪"].notna()].sort_values("P&L ₪")
        if not pnl_valid.empty:
            tase_df = pnl_valid[pnl_valid["Mkt"] == "TASE"]
            us_df = pnl_valid[pnl_valid["Mkt"] == "US"]

            fig_bar = go.Figure()
            if not tase_df.empty:
                fig_bar.add_trace(go.Bar(
                    x=tase_df["P&L ₪"], y=tase_df["Display"],
                    orientation="h", name="TASE",
                    marker_color=theme.ACCENT_PRIMARY,
                    text=[f"₪{v:+,.0f}" for v in tase_df["P&L ₪"]],
                    textposition="outside",
                ))
            if not us_df.empty:
                fig_bar.add_trace(go.Bar(
                    x=us_df["P&L ₪"], y=us_df["Display"],
                    orientation="h", name="US",
                    marker_color=theme.BM_SP500,
                    text=[f"₪{v:+,.0f}" for v in us_df["P&L ₪"]],
                    textposition="outside",
                ))
            fig_bar.update_layout(
                title="P&L per Position (₪)",
                height=max(300, len(pnl_valid) * 28 + 80),
                margin=dict(t=40, b=20, l=80),
                yaxis=dict(autorange="reversed"),
                barmode="relative",
                legend=dict(orientation="h", y=1.02, yanchor="bottom"),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # ── Position table ───────────────────────────────────────────────────────
    headers = ["Symbol", "Name", "Mkt", "Qty", "Cost ₪", "Price ₪",
                "Value ₪", "P&L ₪", "P&L %"]
    alignments = ["l", "l", "l", "r", "r", "r", "r", "r", "r"]
    html_rows = []
    for r in rows:
        pnl_val = r["P&L ₪"]
        pnl_pct_val = r["P&L %"]
        pnl_class = "gain" if (pnl_val is not None and pnl_val >= 0) else "loss"
        html_rows.append([
            r["Symbol"], r["Name"], r["Mkt"],
            f'{r["Qty"]:,.4f}',
            f'₪{r["Cost ₪"]:,.2f}' if r["Cost ₪"] else "—",
            f'₪{r["Price ₪"]:,.2f}' if r["Price ₪"] else "—",
            f'₪{r["Value ₪"]:,.2f}' if r["Value ₪"] else "—",
            f'<span class="pnl-pill {pnl_class}">₪{pnl_val:+,.2f}</span>' if pnl_val is not None else "—",
            f'<span class="pnl-pill {pnl_class}">{pnl_pct_val:+.2f}%</span>' if pnl_pct_val is not None else "—",
        ])
    st.markdown(html_table(headers, html_rows, alignments),
                unsafe_allow_html=True)
