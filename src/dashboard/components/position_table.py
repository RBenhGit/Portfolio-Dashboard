"""Reusable styled position table component."""
import pandas as pd
import streamlit as st
from typing import Optional


def _color_pnl(val: float) -> str:
    color = "#2ecc71" if val >= 0 else "#e74c3c"
    return f"color: {color}; font-weight: bold"


def render_position_table(
    positions: dict,
    currency_symbol: str,
    prices: Optional[dict] = None,
) -> None:
    """Render a styled position table.

    Args:
        positions: {symbol: Position}
        currency_symbol: '₪' or '$'
        prices: optional {symbol: price} override (uses position.market_price if None)
    """
    if not positions:
        st.info("No open positions.")
        return

    rows = []
    for sym, pos in positions.items():
        price = (prices or {}).get(sym) if prices else pos.market_price
        market_value = (price * pos.quantity) if price else None
        cost_value = pos.total_invested
        pnl = (market_value - cost_value) if market_value is not None else None
        pnl_pct = (pnl / cost_value * 100) if (pnl is not None and cost_value > 0) else None

        rows.append({
            "Symbol": sym,
            "Name": pos.security_name or "—",
            "Mkt": pos.market,
            "Qty": pos.quantity,
            f"Avg Cost ({currency_symbol})": pos.average_cost,
            f"Price ({currency_symbol})": price,
            f"Value ({currency_symbol})": market_value,
            f"P&L ({currency_symbol})": pnl,
            "P&L %": pnl_pct,
        })

    df = pd.DataFrame(rows)

    # Style
    def style_row(row):
        styles = [""] * len(row)
        pnl_col = f"P&L ({currency_symbol})"
        if pnl_col in row.index and pd.notna(row[pnl_col]):
            color = "#2ecc71" if row[pnl_col] >= 0 else "#e74c3c"
            idx = list(row.index).index(pnl_col)
            styles[idx] = f"color: {color}; font-weight: bold"
            pct_col = "P&L %"
            if pct_col in row.index:
                styles[list(row.index).index(pct_col)] = f"color: {color}; font-weight: bold"
        return styles

    fmt = {
        "Qty": "{:,.4f}",
        f"Avg Cost ({currency_symbol})": f"{currency_symbol}{{:,.2f}}",
        f"Price ({currency_symbol})": f"{currency_symbol}{{:,.2f}}",
        f"Value ({currency_symbol})": f"{currency_symbol}{{:,.2f}}",
        f"P&L ({currency_symbol})": f"{currency_symbol}{{:,.2f}}",
        "P&L %": "{:+.2f}%",
    }

    styled = (
        df.style
        .apply(style_row, axis=1)
        .format(fmt, na_rep="—")
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)
