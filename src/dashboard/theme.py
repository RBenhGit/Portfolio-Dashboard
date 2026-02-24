"""Centralized theme palette and Plotly template for the IBI Portfolio Dashboard."""
import plotly.graph_objects as go
import plotly.io as pio

# ── Background & Surface Colors ──────────────────────────────────────────
BG_PRIMARY = "#FAFBFE"
BG_SECONDARY = "#F0F4FF"
BG_SURFACE = "#FFFFFF"
BG_SURFACE_HOVER = "#EEF2FF"
BORDER_SUBTLE = "#E0E7FF"
BORDER_ACCENT = "#C7D2FE"

# ── Text Colors ──────────────────────────────────────────────────────────
TEXT_PRIMARY = "#1E293B"
TEXT_SECONDARY = "#64748B"
TEXT_MUTED = "#94A3B8"

# ── Semantic Colors ──────────────────────────────────────────────────────
PROFIT = "#10B981"
PROFIT_BG = "rgba(16, 185, 129, 0.12)"
LOSS = "#EF4444"
LOSS_BG = "rgba(239, 68, 68, 0.10)"
NEUTRAL = "#64748B"
WARNING = "#F59E0B"
INFO = "#06B6D4"

# ── Accent Colors ────────────────────────────────────────────────────────
ACCENT_PRIMARY = "#6366F1"
ACCENT_SECONDARY = "#EC4899"
ACCENT_TERTIARY = "#F59E0B"

# ── Chart Color Sequence ─────────────────────────────────────────────────
CHART_COLORS = [
    "#6366F1", "#EC4899", "#F59E0B", "#10B981", "#06B6D4",
    "#8B5CF6", "#F97316", "#14B8A6", "#E879F9", "#3B82F6",
    "#84CC16", "#FB923C",
]

# ── Benchmark Colors ─────────────────────────────────────────────────────
BM_PORTFOLIO = "#6366F1"
BM_SP500 = "#F59E0B"
BM_TA125 = "#EC4899"

# ── Options Direction Colors ─────────────────────────────────────────────
OPT_LONG = PROFIT
OPT_SHORT = LOSS
OPT_CLOSED = NEUTRAL


def plotly_template() -> go.layout.Template:
    """Return a light Plotly template matching the dashboard theme."""
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, -apple-system, sans-serif",
                      color=TEXT_PRIMARY, size=13),
            title=dict(font=dict(size=16, color=TEXT_PRIMARY),
                       x=0, xanchor="left"),
            xaxis=dict(gridcolor=BORDER_SUBTLE, zerolinecolor=BORDER_ACCENT,
                       tickfont=dict(color=TEXT_SECONDARY)),
            yaxis=dict(gridcolor=BORDER_SUBTLE, zerolinecolor=BORDER_ACCENT,
                       tickfont=dict(color=TEXT_SECONDARY)),
            colorway=CHART_COLORS,
            hoverlabel=dict(
                bgcolor=BG_SURFACE,
                bordercolor=BORDER_ACCENT,
                font=dict(color=TEXT_PRIMARY, size=13),
            ),
            legend=dict(
                bgcolor="rgba(0,0,0,0)",
                bordercolor=BORDER_SUBTLE,
                borderwidth=1,
                font=dict(color=TEXT_SECONDARY),
            ),
            margin=dict(t=50, b=30, l=60, r=20),
        )
    )


def apply_theme():
    """Register the custom Plotly template as default."""
    pio.templates["ibi_dark"] = plotly_template()
    pio.templates.default = "ibi_dark"


def pnl_color(value: float) -> str:
    """Return PROFIT or LOSS color based on sign."""
    return PROFIT if value >= 0 else LOSS


def pnl_bg_color(value: float) -> str:
    """Return PROFIT_BG or LOSS_BG based on sign."""
    return PROFIT_BG if value >= 0 else LOSS_BG
