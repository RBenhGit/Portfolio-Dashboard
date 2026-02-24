"""Options positions tab renderer."""
import pandas as pd
import streamlit as st

from src.dashboard import theme
from src.dashboard.styles import section_header, html_table
from src.models.position import Position

_QTY_EPS = 0.001


def render(options_nis: dict, options_usd: dict) -> None:
    """Render the options positions tab."""
    st.markdown(section_header("Options Positions"), unsafe_allow_html=True)

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

    use_interactive = st.toggle("Interactive table", value=False, key="options_tbl")

    if use_interactive:
        df = pd.DataFrame(rows)

        def _color_direction(val):
            colors = {"LONG": theme.OPT_LONG, "SHORT": theme.OPT_SHORT,
                      "CLOSED": theme.OPT_CLOSED}
            color = colors.get(val, theme.OPT_CLOSED)
            return f"color: {color}; font-weight: bold"

        styled = df.style.applymap(_color_direction, subset=["Direction"])
        styled = styled.format({
            "Quantity": "{:,.0f}",
            "Avg Cost": "{:,.2f}",
            "Total Invested": "{:,.2f}",
        })
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        headers = ["Symbol", "Name", "Currency", "Direction", "Quantity",
                    "Avg Cost", "Total Invested"]
        alignments = ["l", "l", "l", "l", "r", "r", "r"]

        html_rows = []
        for r in rows:
            direction = r["Direction"]
            badge_class = {"LONG": "long", "SHORT": "short", "CLOSED": "closed"}.get(
                direction, "closed")
            badge_html = f'<span class="direction-badge {badge_class}">{direction}</span>'

            html_rows.append([
                r["Symbol"],
                r["Name"],
                r["Currency"],
                badge_html,
                f'{r["Quantity"]:,.0f}',
                f'{r["Avg Cost"]:,.2f}',
                f'{r["Total Invested"]:,.2f}',
            ])

        st.markdown(html_table(headers, html_rows, alignments),
                    unsafe_allow_html=True)
