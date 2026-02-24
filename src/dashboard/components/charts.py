"""Plotly charts for portfolio visualization."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from typing import Optional

from src.database import repository
from src.dashboard import theme


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
        color_discrete_sequence=theme.CHART_COLORS,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label",
                      hovertemplate="<b>%{label}</b><br>Value: %{value:,.0f}<br>%{percent}<extra></extra>")
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
            colors.append(theme.PROFIT if pnl >= 0 else theme.LOSS)

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


def allocation_treemap(
    positions: dict,
    prices: dict,
    currency_symbol: str,
    title: str = "Portfolio Composition",
    fx_rate: float = 1.0,
) -> Optional[go.Figure]:
    """Treemap chart showing portfolio allocation, colored by P&L %.

    When *fx_rate* != 1.0, non-TASE (USD) positions are converted to NIS
    so that all values share a common currency.
    """
    labels, values, parents, colors = [], [], [], []
    for sym, pos in positions.items():
        price = prices.get(sym)
        if price is not None and pos.quantity > 0:
            multiplier = fx_rate if getattr(pos, "market", "") != "TASE" else 1.0
            mv = price * pos.quantity * multiplier
            if mv > 0:
                pnl_pct = ((price - pos.average_cost) / pos.average_cost * 100
                           if pos.average_cost > 0 else 0)
                labels.append(_display_label(sym, pos))
                values.append(mv)
                parents.append("")
                colors.append(pnl_pct)

    if not values:
        return None

    fig = go.Figure(go.Treemap(
        labels=labels,
        values=values,
        parents=parents,
        marker=dict(
            colors=colors,
            colorscale=[[0, theme.LOSS], [0.5, theme.BG_SURFACE], [1, theme.PROFIT]],
            cmid=0,
            line=dict(width=2, color=theme.BG_PRIMARY),
        ),
        textinfo="label+percent parent",
        hovertemplate=("<b>%{label}</b><br>"
                       f"Value: {currency_symbol}%{{value:,.0f}}<br>"
                       "P&L: %{color:+.1f}%<extra></extra>"),
    ))
    fig.update_layout(title=title, height=450, margin=dict(t=50, b=10, l=10, r=10))
    return fig


def waterfall_pnl(
    positions: dict,
    prices: dict,
    currency_symbol: str,
    fx_rate: float = 1.0,
) -> Optional[go.Figure]:
    """Waterfall chart showing P&L contribution per position.

    When *fx_rate* != 1.0, non-TASE (USD) positions are converted to NIS.
    """
    items = []
    for sym, pos in positions.items():
        price = prices.get(sym)
        if price is not None and pos.average_cost > 0:
            multiplier = fx_rate if getattr(pos, "market", "") != "TASE" else 1.0
            pnl = (price - pos.average_cost) * pos.quantity * multiplier
            items.append((_display_label(sym, pos), pnl))

    if not items:
        return None

    items.sort(key=lambda x: x[1], reverse=True)
    names = [i[0] for i in items] + ["Total"]
    pnls = [i[1] for i in items] + [sum(i[1] for i in items)]
    measures = ["relative"] * len(items) + ["total"]

    fig = go.Figure(go.Waterfall(
        x=names, y=pnls, measure=measures,
        increasing=dict(marker_color=theme.PROFIT),
        decreasing=dict(marker_color=theme.LOSS),
        totals=dict(marker_color=theme.ACCENT_SECONDARY),
        connector=dict(line=dict(color=theme.BORDER_SUBTLE)),
        textposition="outside",
        text=[f"{currency_symbol}{v:+,.0f}" for v in pnls],
    ))
    fig.update_layout(
        title="P&L Breakdown (Waterfall)",
        height=400,
        margin=dict(t=50, b=80),
        xaxis_tickangle=-45,
    )
    return fig


def area_chart_with_gradient(
    series: pd.Series,
    name: str = "Portfolio Value",
    color: str = None,
) -> go.Figure:
    """Line chart with gradient fill underneath."""
    c = color or theme.ACCENT_PRIMARY
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series.index, y=series.values,
        mode="lines", name=name,
        line=dict(color=c, width=2.5),
        fill="tozeroy",
        fillcolor=f"rgba({r}, {g}, {b}, 0.08)",
        hovertemplate=(f"<b>{name}</b><br>"
                       "Date: %{x|%Y-%m-%d}<br>"
                       "Value: %{y:,.0f}<extra></extra>"),
    ))
    fig.update_layout(height=420, margin=dict(t=40, b=20),
                      yaxis_title="Value (₪)")
    return fig


def drawdown_chart(series: pd.Series) -> go.Figure:
    """Underwater/drawdown chart."""
    cummax = series.cummax()
    drawdown = (series - cummax) / cummax * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=drawdown.index, y=drawdown.values,
        fill="tozeroy",
        fillcolor="rgba(255, 71, 87, 0.15)",
        line=dict(color=theme.LOSS, width=1.5),
        name="Drawdown",
        hovertemplate="Drawdown: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Drawdown (Underwater Plot)",
        yaxis_title="Drawdown %",
        height=250,
        margin=dict(t=40, b=20),
        yaxis=dict(ticksuffix="%"),
    )
    return fig


def monthly_returns_heatmap(series: pd.Series) -> Optional[go.Figure]:
    """Calendar-style monthly returns heatmap."""
    if len(series) < 30:
        return None

    monthly = series.resample("ME").last().pct_change() * 100
    monthly = monthly.dropna()
    if monthly.empty:
        return None

    df = pd.DataFrame({
        "year": monthly.index.year,
        "month": monthly.index.month,
        "return": monthly.values,
    })
    pivot = df.pivot_table(index="year", columns="month", values="return")
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[month_labels[i - 1] for i in pivot.columns],
        y=pivot.index.astype(str),
        colorscale=[[0, theme.LOSS], [0.5, theme.BG_SURFACE], [1, theme.PROFIT]],
        zmid=0,
        text=[[f"{v:.1f}%" if pd.notna(v) else "" for v in row]
              for row in pivot.values],
        texttemplate="%{text}",
        hovertemplate="Year: %{y}<br>Month: %{x}<br>Return: %{z:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Monthly Returns Heatmap",
        height=max(200, len(pivot) * 45 + 100),
        margin=dict(t=50, b=20),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def monthly_returns_bar(series: pd.Series) -> Optional[go.Figure]:
    """Monthly returns bar chart."""
    if len(series) < 30:
        return None

    monthly = series.resample("ME").last().pct_change() * 100
    monthly = monthly.dropna()
    if monthly.empty:
        return None

    colors = [theme.PROFIT if v >= 0 else theme.LOSS for v in monthly.values]
    fig = go.Figure(go.Bar(
        x=monthly.index, y=monthly.values,
        marker_color=colors,
        text=[f"{v:+.1f}%" for v in monthly.values],
        textposition="outside",
        hovertemplate="Month: %{x|%b %Y}<br>Return: %{y:+.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title="Monthly Returns",
        yaxis_title="Return %",
        height=350,
        margin=dict(t=50, b=20),
        yaxis=dict(ticksuffix="%"),
    )
    return fig


def rolling_sharpe_chart(series: pd.Series, window: int = 60) -> Optional[go.Figure]:
    """Rolling Sharpe ratio chart."""
    daily = series.resample("D").ffill()
    returns = daily.pct_change().dropna()
    if len(returns) < window:
        return None

    daily_rf = 0.04 / 252
    excess = returns - daily_rf
    rolling_mean = excess.rolling(window).mean()
    rolling_std = excess.rolling(window).std()
    rolling_sharpe = (rolling_mean / rolling_std * np.sqrt(252)).dropna()

    if rolling_sharpe.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rolling_sharpe.index, y=rolling_sharpe.values,
        mode="lines", name=f"{window}d Rolling Sharpe",
        line=dict(color=theme.ACCENT_SECONDARY, width=2),
    ))
    fig.add_hline(y=0, line_dash="dot", line_color=theme.TEXT_MUTED)
    fig.add_hline(y=1, line_dash="dot", line_color=theme.PROFIT, opacity=0.3,
                  annotation_text="Sharpe = 1",
                  annotation_font_color=theme.TEXT_MUTED)
    fig.update_layout(
        title=f"Rolling Sharpe Ratio ({window}-day)",
        yaxis_title="Sharpe Ratio",
        height=300,
        margin=dict(t=50, b=20),
    )
    return fig
