"""End-to-end test for src/portfolio/ingestion.py — fixture Excel → real
classifier → in-memory SQLite → real builder. Network calls (FX, prices) and
config/initial_positions.json are patched out so the test is hermetic."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.database.db import create_schema

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
