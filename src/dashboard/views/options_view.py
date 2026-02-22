"""Options positions tab renderer."""
import pandas as pd
import streamlit as st
from src.models.position import Position

_QTY_EPS = 0.001  # threshold for "open" position


def render(options_nis: dict, options_usd: dict) -> None:
    """Render the options positions tab.

    Args:
        options_nis: {symbol: Position} for NIS-denominated options
        options_usd: {symbol: Position} for USD-denominated options
    """
    st.subheader("Options Positions")

    if not options_nis and not options_usd:
        st.info("No option positions.")
        return

    all_positions = list(options_nis.values()) + list(options_usd.values())

    # Filter toggle
    open_only = st.toggle("Open positions only", value=True)

    if open_only:
        all_positions = [p for p in all_positions if abs(p.quantity) > _QTY_EPS]

    if not all_positions:
        st.info("No open option positions.")
        return

    # Summary metrics
    long_count = sum(1 for p in all_positions if p.quantity > _QTY_EPS)
    short_count = sum(1 for p in all_positions if p.quantity < -_QTY_EPS)
    total_capital = sum(abs(p.total_invested) for p in all_positions)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Positions", len(all_positions))
    m2.metric("Long / Short", f"{long_count} / {short_count}")
    m3.metric("Total Capital", f"{total_capital:,.0f}")

    # Build rows
    rows = []
    for pos in all_positions:
        qty_abs = abs(pos.quantity)
        if qty_abs < _QTY_EPS:
            direction = "CLOSED"
            avg_cost = pos.average_cost
        elif pos.quantity > 0:
            direction = "LONG"
            avg_cost = pos.average_cost
        else:
            direction = "SHORT"
            avg_cost = abs(pos.total_invested) / qty_abs if qty_abs else 0.0
        rows.append({
            "Symbol": pos.security_symbol,
            "Name": pos.security_name or "",
            "Currency": pos.currency,
            "Direction": direction,
            "Quantity": qty_abs,
            "Avg Cost": round(avg_cost, 2),
            "Total Invested": round(abs(pos.total_invested), 2),
        })

    df = pd.DataFrame(rows)

    # Style direction column
    def _color_direction(val):
        colors = {"LONG": "#2ecc71", "SHORT": "#e74c3c", "CLOSED": "#95a5a6"}
        color = colors.get(val, "#95a5a6")
        return f"color: {color}; font-weight: bold"

    styled = df.style.applymap(_color_direction, subset=["Direction"])
    styled = styled.format({
        "Quantity": "{:,.0f}",
        "Avg Cost": "{:,.2f}",
        "Total Invested": "{:,.2f}",
    })

    st.dataframe(styled, use_container_width=True, hide_index=True)
