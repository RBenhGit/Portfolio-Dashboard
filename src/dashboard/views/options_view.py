"""Options open-positions tab renderer."""
import pandas as pd
import streamlit as st
from src.models.position import Position


def render(options_nis: dict, options_usd: dict) -> None:
    """Render the options open-positions tab.

    Args:
        options_nis: {symbol: Position} for NIS-denominated options
        options_usd: {symbol: Position} for USD-denominated options
    """
    st.subheader("Options Open Positions")

    if not options_nis and not options_usd:
        st.info("No open option positions.")
        return

    all_positions = list(options_nis.values()) + list(options_usd.values())

    # Summary metrics
    long_count = sum(1 for p in all_positions if p.quantity > 0)
    short_count = sum(1 for p in all_positions if p.quantity < 0)
    total_capital = sum(abs(p.total_invested) for p in all_positions)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Positions", len(all_positions))
    m2.metric("Long / Short", f"{long_count} / {short_count}")
    m3.metric("Total Capital", f"{total_capital:,.0f}")

    # Build rows
    rows = []
    for pos in all_positions:
        is_long = pos.quantity > 0
        qty_abs = abs(pos.quantity)
        if pos.quantity < 0:
            avg_cost = abs(pos.total_invested) / qty_abs if qty_abs else 0.0
        else:
            avg_cost = pos.average_cost
        rows.append({
            "Symbol": pos.security_symbol,
            "Name": pos.security_name or "",
            "Currency": pos.currency,
            "Direction": "LONG" if is_long else "SHORT",
            "Quantity": qty_abs,
            "Avg Cost": round(avg_cost, 2),
            "Total Invested": round(abs(pos.total_invested), 2),
        })

    df = pd.DataFrame(rows)

    # Style direction column
    def _color_direction(val):
        color = "#2ecc71" if val == "LONG" else "#e74c3c"
        return f"color: {color}; font-weight: bold"

    styled = df.style.applymap(_color_direction, subset=["Direction"])
    styled = styled.format({
        "Quantity": "{:,.0f}",
        "Avg Cost": "{:,.2f}",
        "Total Invested": "{:,.2f}",
    })

    st.dataframe(styled, use_container_width=True, hide_index=True)
