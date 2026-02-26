"""Reusable styled position table component."""
import streamlit as st
from typing import Optional

from src.dashboard.styles import html_table


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
            "Avg Cost": pos.average_cost,
            "Price": price,
            "Value": market_value,
            "P&L": pnl,
            "P&L %": pnl_pct,
        })

    headers = ["Symbol", "Name", "Mkt", "Qty", "Avg Cost", "Price",
                "Value", "P&L", "P&L %"]
    alignments = ["l", "l", "l", "r", "r", "r", "r", "r", "r"]

    html_rows = []
    for r in rows:
        pnl_val = r["P&L"]
        pnl_pct_val = r["P&L %"]
        pnl_class = "gain" if (pnl_val is not None and pnl_val >= 0) else "loss"

        html_rows.append([
            r["Symbol"],
            r["Name"],
            r["Mkt"],
            f'{r["Qty"]:,.4f}',
            f'{currency_symbol}{r["Avg Cost"]:,.2f}' if r["Avg Cost"] else "—",
            f'{currency_symbol}{r["Price"]:,.2f}' if r["Price"] else "—",
            f'{currency_symbol}{r["Value"]:,.2f}' if r["Value"] else "—",
            f'<span class="pnl-pill {pnl_class}">{currency_symbol}{pnl_val:+,.2f}</span>' if pnl_val is not None else "—",
            f'<span class="pnl-pill {pnl_class}">{pnl_pct_val:+.2f}%</span>' if pnl_pct_val is not None else "—",
        ])

    st.markdown(html_table(headers, html_rows, alignments),
                unsafe_allow_html=True)
