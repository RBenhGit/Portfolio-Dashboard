"""End-to-end test for src/portfolio/ingestion.py — fixture Excel → real
classifier → in-memory SQLite → real builder. Network calls (FX, prices) and
config/initial_positions.json are patched out so the test is hermetic."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from dotenv import dotenv_values

from src.database.db import create_schema

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Fetched reports land in pdf_archive/; fall back to the original location.
_PDF_CANDIDATES = [
    PROJECT_ROOT / "Trans_Input" / "pdf_archive" / "IBI__000093395_001810.pdf",
    PROJECT_ROOT / "Trans_Input" / "IBI__000093395_001810.pdf",
]
_REAL_PDF_PATH = next((p for p in _PDF_CANDIDATES if p.exists()), _PDF_CANDIDATES[0])
_ENV = dotenv_values(PROJECT_ROOT / ".env")
_REAL_PDF_PASSWORD = _ENV.get("IBI_PDF_PASSWORD")

_HEBREW_COLS = [
    "תאריך", "סוג פעולה", "שם נייר", "מס' נייר / סימבול", "כמות",
    "שער ביצוע", "מטבע", "עמלת פעולה", "עמלות נלוות",
    'תמורה במט"ח', "תמורה בשקלים", "יתרה שקלית", "אומדן מס רווחי הון",
]


def _make_excel(path, rows):
    pd.DataFrame(rows, columns=_HEBREW_COLS).to_excel(
        str(path), index=False, engine="openpyxl")
    return path


@pytest.fixture
def fixture_xlsx(tmp_path):
    """3 NIS rows (cash-in, buy 10 @ ₪170, sell 5 @ ₪200) + 1 USD buy."""
    return _make_excel(tmp_path / "ibi.xlsx", [
        # newest first, like a real IBI export
        ["04/01/2024", "קניה חול מטח", "Apple", "AAPL", "5", "100", "$",
         "1", "0", "-500", "0", "0", "0"],
        ["03/01/2024", "מכירה שח", "מטריקס", "445015", "5", "20000", "₪",
         "5", "0", "0", "1000", "9300", "0"],
        ["02/01/2024", "קניה שח", "מטריקס", "445015", "10", "17000", "₪",
         "5", "0", "0", "-1700", "8300", "0"],
        ["02/01/2024", "העברה מזומן בשח", "", "", "0", "0", "₪",
         "0", "0", "0", "10000", "10000", "0"],
    ])


class _NonClosingConnection:
    """Shared in-memory connection that survives repository close() calls."""

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


@pytest.fixture
def pipeline_env(tmp_path):
    """Patch DB to in-memory, FX + prices to fixed values, no initial positions."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    wrapper = _NonClosingConnection(conn)
    with patch("src.database.db.get_connection", return_value=wrapper), \
         patch("src.database.repository.get_connection", return_value=wrapper), \
         patch("src.portfolio.ingestion.fetch_historical_fx",
               return_value={"2024-01-02": 3.7, "2024-01-03": 3.7,
                             "2024-01-04": 3.7}), \
         patch("src.portfolio.builder.get_price", return_value=200.0), \
         patch("src.portfolio.builder._INITIAL_POS_PATH",
               tmp_path / "no_initial_positions.json"):
        create_schema()
        yield conn
    conn.close()


class TestIngestPipeline:
    def test_full_pipeline(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        result = ingest(fixture_xlsx)
        assert result["rows_total"] == 4
        assert result["rows_new"] == 4
        assert result["rows_duplicate"] == 0

        portfolio = result["portfolio"]

        # NIS: bought 10, sold 5 → 5 left at avg cost 1700/10 = ₪170
        pos = portfolio["positions_nis"]["445015"]
        assert pos.quantity == pytest.approx(5.0)
        assert pos.average_cost == pytest.approx(170.0)

        # USD: 5 AAPL at $500 total
        aapl = portfolio["positions_usd"]["AAPL"]
        assert aapl.quantity == pytest.approx(5.0)
        assert aapl.total_invested == pytest.approx(500.0)

        # NIS cash follows IBI's running balance column (last = 9300)
        assert portfolio["nis_cash"] == pytest.approx(9300.0)

    def test_realized_trade_recorded(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)
        rows = pipeline_env.execute("SELECT * FROM realized_trades").fetchall()
        assert len(rows) == 1
        # sold 5 @ ₪200 against avg cost ₪170 → ₪150 realized
        assert rows[0]["realized_pnl"] == pytest.approx(150.0)

    def test_fx_backfilled_for_usd_cost_basis(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)
        row = pipeline_env.execute(
            "SELECT fx_rate_on_date, cost_basis, cost_basis_nis "
            "FROM transactions WHERE security_symbol='AAPL'").fetchone()
        assert row["fx_rate_on_date"] == pytest.approx(3.7)
        assert row["cost_basis"] == pytest.approx(500.0)
        assert row["cost_basis_nis"] == pytest.approx(500.0 * 3.7)

    def test_daily_state_written_per_date(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)
        n = pipeline_env.execute(
            "SELECT COUNT(*) FROM daily_portfolio_state").fetchone()[0]
        # builder records state at each date boundary (final date is recorded
        # at end of pass)
        assert n >= 2

    def test_reingest_same_file_dedups(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)
        result = ingest(fixture_xlsx)
        assert result["rows_new"] == 0
        assert result["rows_duplicate"] == 4
        n = pipeline_env.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert n == 4

    def test_import_logged(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)
        row = pipeline_env.execute("SELECT * FROM import_log").fetchone()
        assert row["source_file"] == "ibi.xlsx"
        assert row["rows_new"] == 4


@pytest.fixture
def pdf_pipeline_env(tmp_path):
    """Same hermetic setup as pipeline_env, but with FX stubbed generically
    (any date -> 3.7) since the real PDF's transaction dates aren't known
    ahead of time the way the small Excel fixture's are."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    wrapper = _NonClosingConnection(conn)

    def _fake_fx(dates):
        return {d: 3.7 for d in dates}

    with patch("src.database.db.get_connection", return_value=wrapper), \
         patch("src.database.repository.get_connection", return_value=wrapper), \
         patch("src.portfolio.ingestion.fetch_historical_fx", side_effect=_fake_fx), \
         patch("src.portfolio.builder.get_price", return_value=200.0), \
         patch("src.portfolio.builder._INITIAL_POS_PATH",
               tmp_path / "no_initial_positions.json"):
        create_schema()
        yield conn
    conn.close()


@pytest.mark.skipif(
    not _REAL_PDF_PATH.exists() or not _REAL_PDF_PASSWORD,
    reason="Real sample PDF or IBI_PDF_PASSWORD not available in this environment",
)
class TestIngestPdfSource:
    """Confirms ingest() dispatches .pdf sources to read_pdf() and that
    clean PDF-parsed rows flow through the same classify/dedup/build path
    as Excel rows -- no parallel ingestion logic."""

    def test_pdf_ingest_inserts_clean_rows_only(self, pdf_pipeline_env):
        from src.portfolio.ingestion import ingest

        result = ingest(_REAL_PDF_PATH, pdf_password=_REAL_PDF_PASSWORD)

        assert result["rows_new"] > 0
        # Only rows the converter could express in the app's vocabulary are
        # inserted; anything quarantined must NOT reach the table. (This
        # previously asserted quarantine was non-empty, encoding the old
        # cluster-over-merge bug that lost ~37% of rows.)
        n = pdf_pipeline_env.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert n == result["rows_new"]

    def test_pdf_ingest_reingest_dedups(self, pdf_pipeline_env):
        from src.portfolio.ingestion import ingest

        first = ingest(_REAL_PDF_PATH, pdf_password=_REAL_PDF_PASSWORD)
        second = ingest(_REAL_PDF_PATH, pdf_password=_REAL_PDF_PASSWORD)

        assert second["rows_new"] == 0
        assert second["rows_duplicate"] == first["rows_new"]

    def test_pdf_ingest_msft_position_built(self, pdf_pipeline_env):
        from src.portfolio.ingestion import ingest

        result = ingest(_REAL_PDF_PATH, pdf_password=_REAL_PDF_PASSWORD)
        # MSFT sold (qty -2) via the PDF's daily transaction log; confirms
        # the translated tx_type + extracted ticker flow all the way
        # through classify() -> builder.build() into a real position/trade,
        # not just a row in the transactions table.
        portfolio = result["portfolio"]
        realized_symbols = {
            r["security_symbol"] for r in
            pdf_pipeline_env.execute("SELECT security_symbol FROM realized_trades").fetchall()
        }
        positions_usd = portfolio["positions_usd"]
        assert "MSFT" in realized_symbols or "MSFT" in positions_usd


class TestSkipBuildWhenUnchanged:
    """A re-fetched PDF that inserts nothing must not trigger the full
    rebuild: builder.build() truncates daily_portfolio_state and
    realized_trades and recomputes every transaction (~8 min in production).
    import_log ids 16/17 were two such no-op runs that each paid it."""

    def test_rebuild_skipped_when_no_new_rows(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)  # first import populates

        with patch("src.portfolio.builder.build") as mock_build:
            result = ingest(fixture_xlsx, skip_build_if_unchanged=True)

        assert result["rows_new"] == 0
        assert result["rows_duplicate"] == 4
        mock_build.assert_not_called()

    def test_rebuild_runs_when_rows_are_new(self, fixture_xlsx, pipeline_env):
        from src.portfolio.ingestion import ingest

        with patch("src.portfolio.builder.build") as mock_build:
            mock_build.return_value = {}
            ingest(fixture_xlsx, skip_build_if_unchanged=True)

        mock_build.assert_called_once()

    def test_default_still_rebuilds_unconditionally(self, fixture_xlsx, pipeline_env):
        # The Streamlit callers rely on the old behaviour.
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)
        with patch("src.portfolio.builder.build") as mock_build:
            mock_build.return_value = {}
            ingest(fixture_xlsx)

        mock_build.assert_called_once()


class TestWasAlreadyImported:
    """The fetcher has no memory of what it ingested, so run_import.py asks
    import_log before re-parsing a report it has already imported."""

    def test_false_for_unseen_file(self, pipeline_env):
        from src.database.repository import was_already_imported

        assert was_already_imported("never_seen.pdf") is False

    def test_true_after_a_successful_import(self, fixture_xlsx, pipeline_env):
        from src.database.repository import was_already_imported
        from src.portfolio.ingestion import ingest

        ingest(fixture_xlsx)
        assert was_already_imported(fixture_xlsx.name) is True

    def test_zero_row_import_does_not_block_a_retry(self, pipeline_env):
        # A prior run that inserted nothing may have been partial or failed;
        # it must not permanently lock the file out.
        from src.database import repository
        from src.database.repository import was_already_imported

        repository.log_import("partial.pdf", rows_total=10, rows_new=0,
                              rows_duplicate=0)
        assert was_already_imported("partial.pdf") is False
