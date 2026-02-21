"""Plotly charts for portfolio visualization."""
import plotly.graph_objects as go
import plotly.express as px
from typing import Optional

from src.database import repository


def _display_label(sym: str, pos) -> str:
    """Resolve a human-readable label for chart display.

    TASE stocks: use resolved ticker (e.g. 'MTRX') from tase_symbol_map,
    falling back to security_name, then raw symbol.
    US stocks: use the symbol as-is.
    """
    if pos.market == "TASE":
        mapping = repository.get_tase_symbol(sym)
        if mapping and mapping.get("td_symbol"):
            return mapping["td_symbol"]
        if pos.security_name:
            return pos.security_name
    return sym


def allocation_pie(
    positions: dict,
    prices: dict,
    currency_symbol: str,
    title: str = "Allocation",
) -> Optional[go.Figure]:
    """Pie chart of portfolio allocation by market value."""
    labels, values = [], []
    for sym, pos in positions.items():
        price = prices.get(sym)
        if price is not None:
            mv = price * pos.quantity
            if mv > 0:
                labels.append(_display_label(sym, pos))
                values.append(mv)

    if not values:
        return None

    fig = px.pie(
        names=labels,
        values=values,
        title=title,
        hole=0.35,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(showlegend=True, height=380, margin=dict(t=40, b=10))
    return fig


def pnl_bar(
    positions: dict,
    prices: dict,
    currency_symbol: str,
    title: str = "Unrealized P&L",
) -> Optional[go.Figure]:
    """Horizontal bar chart of unrealized P&L per position."""
    syms, pnls, colors = [], [], []
    for sym, pos in positions.items():
        price = prices.get(sym)
        if price is not None and pos.average_cost > 0:
            pnl = (price - pos.average_cost) * pos.quantity
            syms.append(_display_label(sym, pos))
            pnls.append(pnl)
            colors.append("#2ecc71" if pnl >= 0 else "#e74c3c")

    if not syms:
        return None

    fig = go.Figure(go.Bar(
        x=pnls,
        y=syms,
        orientation="h",
        marker_color=colors,
        text=[f"{currency_symbol}{p:+,.0f}" for p in pnls],
        textposition="outside",
    ))
    fig.update_layout(
        title=title,
        xaxis_title=f"P&L ({currency_symbol})",
        height=max(300, len(syms) * 30 + 80),
        margin=dict(t=40, b=20, l=80),
        yaxis=dict(autorange="reversed"),
    )
    return fig
