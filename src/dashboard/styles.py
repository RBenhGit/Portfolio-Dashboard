"""Centralized CSS styles for the IBI Portfolio Dashboard."""

from src.dashboard import theme


def get_all_styles() -> str:
    """Return the complete CSS stylesheet as a string."""
    return f"""<style>
/* ── Font Imports ─────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Base Typography ──────────────────────────────────────────────────── */
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}}

/* ── Metric Cards — Soft Glassmorphism ────────────────────────────────── */
[data-testid="stMetric"] {{
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(240, 244, 255, 0.7));
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(199, 210, 254, 0.6);
    border-radius: 14px;
    padding: 16px 20px;
    box-shadow: 0 4px 16px rgba(99, 102, 241, 0.08);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
[data-testid="stMetric"]:hover {{
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(99, 102, 241, 0.15);
    border-color: rgba(99, 102, 241, 0.4);
}}
[data-testid="stMetricLabel"] {{
    color: {theme.TEXT_SECONDARY};
    font-size: 0.78rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
[data-testid="stMetricValue"] {{
    font-size: 1.4rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    animation: fadeInUp 0.5s ease-out;
}}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    min-width: 260px;
    max-width: 300px;
    background: linear-gradient(180deg, #F0F4FF 0%, #E8EEFF 100%);
    border-right: 1px solid {theme.BORDER_SUBTLE};
}}
[data-testid="stSidebar"] [data-testid="stFileUploader"] section {{
    flex-direction: column;
}}
[data-testid="stSidebar"] [data-testid="stFileUploader"] section > button {{
    width: 100%;
    margin-top: 0.5rem;
}}

/* ── Tabs ─────────────────────────────────────────────────────────────── */
button[data-baseweb="tab"] {{
    font-weight: 500;
    font-size: 0.9rem;
    color: {theme.TEXT_SECONDARY};
    border-bottom: 2px solid transparent;
    transition: all 0.3s ease;
    padding: 10px 20px;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    color: {theme.ACCENT_PRIMARY};
    border-bottom: 2px solid {theme.ACCENT_PRIMARY};
    font-weight: 600;
}}
button[data-baseweb="tab"]:hover {{
    color: {theme.TEXT_PRIMARY};
}}

/* ── Scrollbar ────────────────────────────────────────────────────────── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: {theme.BG_PRIMARY}; }}
::-webkit-scrollbar-thumb {{ background: {theme.BORDER_ACCENT}; border-radius: 3px; }}
::-webkit-scrollbar-thumb:hover {{ background: {theme.ACCENT_PRIMARY}; }}

/* ── DataFrames ───────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
    border: 1px solid {theme.BORDER_SUBTLE};
    border-radius: 8px;
    overflow: hidden;
}}

/* ── Dividers ─────────────────────────────────────────────────────────── */
hr {{
    border-color: {theme.BORDER_SUBTLE} !important;
    opacity: 0.5;
}}

/* ── Section Headers ──────────────────────────────────────────────────── */
.section-header {{
    font-size: 1.1rem;
    font-weight: 600;
    color: {theme.TEXT_PRIMARY};
    padding-bottom: 8px;
    border-bottom: 2px solid {theme.ACCENT_PRIMARY};
    margin-bottom: 16px;
    display: inline-block;
}}

/* ── Status Dot ───────────────────────────────────────────────────────── */
@keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
}}
.status-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse 2s ease-in-out infinite;
}}
.status-dot.connected {{ background: {theme.PROFIT}; }}
.status-dot.disconnected {{ background: {theme.LOSS}; }}

/* ── Animations ───────────────────────────────────────────────────────── */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}

/* ── Custom HTML Tables ───────────────────────────────────────────────── */
.custom-table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid {theme.BORDER_SUBTLE};
    margin: 8px 0;
}}
.custom-table thead th {{
    background: {theme.BG_SECONDARY};
    color: {theme.TEXT_SECONDARY};
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 12px 16px;
    text-align: left;
    border-bottom: 2px solid {theme.BORDER_SUBTLE};
}}
.custom-table tbody tr {{
    transition: background 0.2s ease;
}}
.custom-table tbody tr:nth-child(even) {{
    background: rgba(240, 244, 255, 0.5);
}}
.custom-table tbody tr:hover {{
    background: rgba(238, 242, 255, 0.8);
}}
.custom-table tbody td {{
    padding: 10px 16px;
    color: {theme.TEXT_PRIMARY};
    font-size: 0.88rem;
    border-bottom: 1px solid rgba(224, 231, 255, 0.6);
}}
.custom-table .num {{
    text-align: right;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
}}
.custom-table .text-left {{ text-align: left; }}
.custom-table .text-right {{ text-align: right; }}
.pnl-pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
}}
.pnl-pill.gain {{
    background: {theme.PROFIT_BG};
    color: {theme.PROFIT};
}}
.pnl-pill.loss {{
    background: {theme.LOSS_BG};
    color: {theme.LOSS};
}}

/* ── Cash Cards ───────────────────────────────────────────────────────── */
.cash-card {{
    background: {theme.BG_SURFACE};
    border: 1px solid {theme.BORDER_SUBTLE};
    border-radius: 8px;
    padding: 10px 16px;
    color: {theme.TEXT_PRIMARY};
    font-size: 0.9rem;
}}
.cash-card .label {{
    color: {theme.TEXT_SECONDARY};
    font-size: 0.78rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}}
.cash-card .value {{
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    margin-top: 4px;
    font-size: 1.05rem;
}}

/* ── Direction Badges (Options) ───────────────────────────────────────── */
.direction-badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 0.8rem;
}}
.direction-badge.long {{
    background: {theme.PROFIT_BG};
    color: {theme.PROFIT};
}}
.direction-badge.short {{
    background: {theme.LOSS_BG};
    color: {theme.LOSS};
}}
.direction-badge.closed {{
    background: rgba(100, 116, 139, 0.12);
    color: {theme.NEUTRAL};
}}

/* ── Info Boxes ────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {{
    background: {theme.BG_SURFACE};
    border: 1px solid {theme.BORDER_SUBTLE};
    border-radius: 8px;
}}
</style>"""


def metric_card_html(label: str, value: str, delta: str = "",
                     delta_color: str = "") -> str:
    """Return HTML for a custom hero metric card with optional delta indicator."""
    arrow = ""
    if delta:
        is_negative = delta.strip().startswith("-")
        arrow_char = "&#9660;" if is_negative else "&#9650;"
        color = delta_color or (theme.LOSS if is_negative else theme.PROFIT)
        arrow = (f'<div style="color:{color};font-size:0.85rem;'
                 f'font-family:\'JetBrains Mono\',monospace;margin-top:4px;">'
                 f'{arrow_char} {delta}</div>')
    return (
        f'<div style="background:linear-gradient(135deg,rgba(255,255,255,0.9),rgba(240,244,255,0.7));'
        f'backdrop-filter:blur(10px);border:1px solid rgba(199,210,254,0.6);'
        f'border-radius:14px;padding:18px 22px;'
        f'box-shadow:0 4px 16px rgba(99,102,241,0.08);'
        f'transition:transform 0.2s ease;">'
        f'<div style="color:{theme.TEXT_SECONDARY};font-size:0.75rem;font-weight:500;'
        f'text-transform:uppercase;letter-spacing:0.05em;">{label}</div>'
        f'<div style="color:{theme.TEXT_PRIMARY};font-size:1.5rem;font-weight:700;'
        f"font-family:'JetBrains Mono',monospace;margin-top:4px;\">{value}</div>"
        f'{arrow}</div>'
    )


def section_header(title: str) -> str:
    """Return HTML for a styled section header with accent color."""
    return (f'<div style="font-size:1.1rem;font-weight:600;color:{theme.TEXT_PRIMARY};'
            f'padding-bottom:8px;border-bottom:2px solid {theme.ACCENT_PRIMARY};'
            f'margin-bottom:16px;display:inline-block;">{title}</div>')


def html_table(headers: list, rows: list, alignments: list = None) -> str:
    """Build an HTML table string with light theme styling.

    Args:
        headers: column header labels
        rows: list of row data (each row is a list of pre-formatted HTML strings)
        alignments: 'l' for left or 'r' for right per column
    """
    if not alignments:
        alignments = ["l"] * len(headers)

    thead = "<tr>" + "".join(
        f'<th class="{"text-right" if a == "r" else "text-left"}">{h}</th>'
        for h, a in zip(headers, alignments)
    ) + "</tr>"

    tbody_rows = []
    for row in rows:
        cells = "".join(
            f'<td class="{"num" if a == "r" else ""}">{cell}</td>'
            for cell, a in zip(row, alignments)
        )
        tbody_rows.append(f"<tr>{cells}</tr>")

    return (f'<table class="custom-table"><thead>{thead}</thead>'
            f'<tbody>{"".join(tbody_rows)}</tbody></table>')
