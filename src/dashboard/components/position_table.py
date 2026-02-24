"""Reusable styled position table component."""
import pandas as pd
import streamlit as st
from typing import Optional

from src.dashboard import theme
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

    # Toggle between custom HTML and interactive DataFrame
    use_interactive = st.toggle("Interactive table", value=False,
                                key=f"tbl_toggle_{currency_symbol}")

    if use_interactive:
        df = pd.DataFrame(rows)

        def style_row(row):
            styles = [""] * len(row)
            if "P&L" in row.index and pd.notna(row["P&L"]):
                color = theme.PROFIT if row["P&L"] >= 0 else theme.LOSS
                for col in ("P&L", "P&L %"):
                    if col in row.index:
                        styles[list(row.index).index(col)] = f"color: {color}; font-weight: bold"
            return styles

        fmt = {
            "Qty": "{:,.4f}",
            "Avg Cost": f"{currency_symbol}{{:,.2f}}",
            "Price": f"{currency_symbol}{{:,.2f}}",
            "Value": f"{currency_symbol}{{:,.2f}}",
            "P&L": f"{currency_symbol}{{:+,.2f}}",
            "P&L %": "{:+.2f}%",
        }
        styled = df.style.apply(style_row, axis=1).format(fmt, na_rep="—")
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        # Custom HTML table
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
