"""IBI Portfolio Dashboard — Streamlit entry point."""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── App config ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Portfolio Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar styling: narrower sidebar, stacked file-upload button ─────────────
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { min-width: 220px; max-width: 280px; }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] section {
        flex-direction: column;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploader"] section > button {
        width: 100%; margin-top: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Imports (after page config) ───────────────────────────────────────────────
from src.config import EXCEL_PATH, DB_PATH
from src.database.db import create_schema
from src.database import repository
from src.portfolio.ingestion import ingest
from src.portfolio import builder
from src.market.price_fetcher import fetch_prices_for_positions, check_twelvedata_status
from src.dashboard.views import portfolio_view, merged_view, options_view, performance_view, statistics_view


# ── Startup: ensure DB exists and Excel is parsed ─────────────────────────────
@st.cache_resource(show_spinner="Initialising database…")
def _init() -> None:
    create_schema()


@st.cache_data(show_spinner="Loading portfolio from Excel…", ttl=None)
def _initial_ingest() -> dict:
    """Run ingestion on startup if the DB is empty or Excel is new."""
    count = repository.get_transaction_count()
    if count == 0 and EXCEL_PATH.exists():
        logger.info("DB empty — ingesting %s", EXCEL_PATH)
        return ingest(EXCEL_PATH, trigger="startup")
    return {}


_init()
_initial_ingest()


# ── Build current portfolio state ─────────────────────────────────────────────
@st.cache_data(show_spinner="Building portfolio…", ttl=300)
def _get_portfolio() -> dict:
    return builder.build(trigger="display")


@st.cache_data(show_spinner="Fetching prices…", ttl=None)
def _get_prices(positions_nis_keys: tuple, positions_usd_keys: tuple,
                price_date: str = "") -> dict:
    portfolio = _get_portfolio()
    all_pos = {**portfolio.get("positions_nis", {}), **portfolio.get("positions_usd", {})}
    return fetch_prices_for_positions(all_pos, price_date)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Controls")

    # Twelvedata status
    td_ok = check_twelvedata_status()
    st.markdown(
        f"Twelvedata API: {'✅ Connected' if td_ok else '❌ Unavailable'}"
    )

    st.divider()

    # Upload new Excel
    st.subheader("📥 Import Transactions")
    uploaded = st.file_uploader(
        "Upload IBI Excel (.xlsx)", type=["xlsx"], key="uploader"
    )
    if uploaded is not None:
        with st.spinner("Importing…"):
            import tempfile, os
            suffix = Path(uploaded.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name
            try:
                result = ingest(tmp_path, trigger="import")
                st.success(
                    f"✅ {result['rows_new']} new rows imported, "
                    f"{result['rows_duplicate']} duplicates skipped."
                )
                # Invalidate caches
                st.cache_data.clear()
            except Exception as exc:
                st.error(f"Import failed: {exc}")
                logger.exception("Import error")
            finally:
                os.unlink(tmp_path)

    st.divider()

    # Last import info
    last = repository.get_last_import()
    if last:
        st.caption(f"Last import: **{last['source_file']}**")
        st.caption(f"At: {last['imported_at'][:19].replace('T', ' ')} UTC")
        st.caption(f"Added: {last['rows_new']} rows")

    st.divider()

    # Force re-parse
    if st.button("🔄 Force Re-parse Excel"):
        if EXCEL_PATH.exists():
            with st.spinner("Re-parsing…"):
                try:
                    result = ingest(EXCEL_PATH, trigger="force")
                    st.success(f"Re-parse done. {result['rows_new']} new rows.")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Re-parse failed: {exc}")
        else:
            st.error(f"File not found: {EXCEL_PATH}")

    # Refresh prices
    if st.button("⟳ Refresh Prices"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"DB: `{DB_PATH}`")
    st.caption(f"Rows: {repository.get_transaction_count()}")


# ── Main content ─────────────────────────────────────────────────────────────
st.title("📈 Portfolio Dashboard")

portfolio = _get_portfolio()
positions_nis = portfolio.get("positions_nis", {})
positions_usd = portfolio.get("positions_usd", {})
options_nis = portfolio.get("options_nis", {})
options_usd = portfolio.get("options_usd", {})

# Determine the reference date: closing price on the last transaction date
price_date = repository.get_max_transaction_date() or ""
if price_date:
    st.markdown(f"### **Prices as of: {price_date}**")

prices = _get_prices(
    tuple(positions_nis.keys()),
    tuple(positions_usd.keys()),
    price_date,
)

tab_stats, tab_performance, tab_tase, tab_us, tab_merged, tab_options = st.tabs(
    ["📊 Statistics", "📈 Performance", "🏦 TASE (₪)", "🌐 US ($)", "🌍 Merged (₪)", "📋 Options"]
)

with tab_stats:
    statistics_view.render(portfolio, prices, price_date)

with tab_tase:
    portfolio_view.render(
        positions_nis, prices, "₪",
        portfolio.get("nis_cash", 0.0), "TASE Portfolio",
    )

with tab_us:
    portfolio_view.render(
        positions_usd, prices, "$",
        portfolio.get("usd_cash", 0.0), "US Portfolio",
    )

with tab_merged:
    merged_view.render(portfolio, prices, price_date)

with tab_options:
    options_view.render(options_nis, options_usd)

with tab_performance:
    performance_view.render()
