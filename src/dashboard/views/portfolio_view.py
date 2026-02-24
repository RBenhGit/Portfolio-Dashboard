"""Single-market portfolio tab renderer."""
import streamlit as st

from src.dashboard import theme
from src.dashboard.styles import section_header
from src.dashboard.components.position_table import render_position_table
from src.dashboard.components.charts import allocation_pie, allocation_treemap, pnl_bar


def render(positions: dict, prices: dict, currency_symbol: str,
           cash: float, title: str) -> None:
    """Render a single-market portfolio tab at full width."""
    st.markdown(section_header(title), unsafe_allow_html=True)

    filtered_prices = {s: prices.get(s) for s in positions}
    invested = sum(p.total_invested for p in positions.values())
    market_value = sum(
        (prices.get(s) or 0) * p.quantity for s, p in positions.items()
    )
    pnl = market_value - invested
    pnl_pct = (pnl / invested * 100) if invested > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Invested", f"{currency_symbol}{invested:,.0f}")
    m2.metric("Market Value", f"{currency_symbol}{market_value:,.0f}")
    m3.metric("P&L", f"{currency_symbol}{pnl:+,.0f}")
    m4.metric("P&L %", f"{pnl_pct:+.1f}%")

    # Cash card
    st.markdown(f'''<div class="cash-card">
        <div class="label">Cash Balance</div>
        <div class="value">{currency_symbol}{cash:,.2f}</div>
    </div>''', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)

    render_position_table(positions, currency_symbol, filtered_prices)

    # Charts
    chart_type = st.radio("Chart type", ["Treemap", "Donut"],
                          horizontal=True, key=f"chart_{title}")

    col1, col2 = st.columns(2)
    with col1:
        if chart_type == "Treemap":
            fig = allocation_treemap(positions, filtered_prices, currency_symbol,
                                     f"{title} Allocation")
        else:
            fig = allocation_pie(positions, filtered_prices, currency_symbol,
                                 f"{title} Allocation")
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig2 = pnl_bar(positions, filtered_prices, currency_symbol, f"{title} P&L")
        if fig2:
            st.plotly_chart(fig2, use_container_width=True)
