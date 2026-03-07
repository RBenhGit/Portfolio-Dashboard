"""Tests for src/database/repository.py — all CRUD operations with in-memory SQLite."""
import sqlite3
import pytest
from unittest.mock import patch
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Fixture: in-memory DB with full schema
# ---------------------------------------------------------------------------

def _create_in_memory_db():
    """Create an in-memory SQLite DB with the full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, transaction_type TEXT NOT NULL,
    effect TEXT NOT NULL, is_phantom INTEGER NOT NULL DEFAULT 0,
    security_name TEXT, security_symbol TEXT, market TEXT, currency TEXT,
    quantity REAL, share_direction TEXT, share_quantity_abs REAL,
    execution_price_raw REAL, execution_price REAL,
    commission REAL, additional_fees REAL,
    amount_foreign_currency REAL, amount_local_currency REAL,
    balance REAL, capital_gains_tax_estimate REAL,
    cost_basis REAL, cash_flow_nis REAL, cash_flow_usd REAL,
    fx_rate_on_date REAL, cost_basis_nis REAL,
    row_hash TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS fx_rates (
    date TEXT PRIMARY KEY, usd_ils REAL NOT NULL, source TEXT
);
CREATE TABLE IF NOT EXISTS price_cache (
    symbol TEXT NOT NULL, market TEXT NOT NULL, price_date TEXT NOT NULL,
    price REAL NOT NULL, currency TEXT NOT NULL, fetched_at TEXT NOT NULL,
    source TEXT, PRIMARY KEY (symbol, market, price_date)
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL, created_at TEXT NOT NULL, trigger TEXT NOT NULL,
    nis_stocks_value REAL, nis_cash REAL, nis_total REAL,
    usd_stocks_value REAL, usd_cash REAL, usd_total REAL,
    fx_rate REAL, total_nis REAL, realized_pnl_nis REAL, realized_pnl_usd REAL
);
CREATE TABLE IF NOT EXISTS position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES portfolio_snapshots(id),
    security_symbol TEXT NOT NULL, security_name TEXT, market TEXT, currency TEXT,
    quantity REAL, average_cost REAL, total_invested REAL, total_invested_nis REAL,
    market_price REAL, market_value REAL, unrealized_pnl REAL, unrealized_pnl_pct REAL
);
CREATE TABLE IF NOT EXISTS daily_portfolio_state (
    date TEXT PRIMARY KEY, nis_invested REAL, nis_cash REAL, nis_total_cost REAL,
    usd_invested REAL, usd_cash REAL, usd_total_cost REAL,
    fx_rate REAL, total_cost_nis REAL, cum_realized_pnl_nis REAL, cum_realized_pnl_usd REAL,
    nis_market_value REAL, usd_market_value REAL, total_market_value_nis REAL
);
CREATE TABLE IF NOT EXISTS realized_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, security_symbol TEXT NOT NULL, security_name TEXT,
    market TEXT, currency TEXT, quantity_sold REAL, avg_cost REAL,
    sale_price REAL, cost_total REAL, proceeds REAL,
    realized_pnl REAL, realized_pnl_pct REAL
);
CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TEXT NOT NULL, source_file TEXT NOT NULL,
    rows_total INTEGER, rows_new INTEGER, rows_duplicate INTEGER
);
CREATE TABLE IF NOT EXISTS tase_symbol_map (
    ibi_id TEXT PRIMARY KEY, td_symbol TEXT, yf_symbol TEXT, name TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS benchmark_cache (
    symbol TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL,
    fetched_at TEXT NOT NULL, PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS portfolio_current (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);
    """)
    return conn


class _NonClosingConnection:
    """Wrapper that prevents close() from destroying the shared connection."""

    def __init__(self, real_conn):
        self._conn = real_conn

    def close(self):
        pass  # no-op — keep the connection alive between repository calls

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


@pytest.fixture
def mock_conn():
    """Patch get_connection to return a shared in-memory connection."""
    real_conn = _create_in_memory_db()
    wrapper = _NonClosingConnection(real_conn)
    with patch("src.database.repository.get_connection", return_value=wrapper):
        yield real_conn
    real_conn.close()


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

def _sample_tx(row_hash="hash1", date="2024-01-01"):
    from src.database.repository import _TX_COLS
    tx = {c: None for c in _TX_COLS}
    tx.update({
        "date": date, "transaction_type": "קניה שח", "effect": "buy",
        "is_phantom": 0, "security_symbol": "12345", "security_name": "Test",
        "market": "TASE", "currency": "₪", "quantity": 10,
        "share_direction": "add", "share_quantity_abs": 10,
        "execution_price_raw": 17000, "execution_price": 170,
        "cost_basis": 1700, "cash_flow_nis": -1700, "cash_flow_usd": 0,
        "row_hash": row_hash,
    })
    return tx


# ── Transactions ──────────────────────────────────────────────────────────────

class TestTransactions:
    def test_insert_and_count(self, mock_conn):
        from src.database.repository import insert_transactions_deduped, get_transaction_count
        new, dup = insert_transactions_deduped([_sample_tx()])
        assert new == 1
        assert dup == 0
        assert get_transaction_count() == 1

    def test_dedup_by_row_hash(self, mock_conn):
        from src.database.repository import insert_transactions_deduped, get_transaction_count
        insert_transactions_deduped([_sample_tx("hash1")])
        new, dup = insert_transactions_deduped([_sample_tx("hash1")])
        assert new == 0
        assert dup == 1
        assert get_transaction_count() == 1

    def test_different_hashes_both_inserted(self, mock_conn):
        from src.database.repository import insert_transactions_deduped, get_transaction_count
        insert_transactions_deduped([_sample_tx("h1"), _sample_tx("h2")])
        assert get_transaction_count() == 2

    def test_get_all_transactions(self, mock_conn):
        from src.database.repository import insert_transactions_deduped, get_all_transactions
        insert_transactions_deduped([_sample_tx()])
        rows = get_all_transactions()
        assert len(rows) == 1
        assert rows[0]["security_symbol"] == "12345"

    def test_get_max_transaction_date(self, mock_conn):
        from src.database.repository import insert_transactions_deduped, get_max_transaction_date
        insert_transactions_deduped([
            _sample_tx("h1", "2024-01-01"),
            _sample_tx("h2", "2024-06-15"),
        ])
        assert get_max_transaction_date() == "2024-06-15"


# ── FX Rates ──────────────────────────────────────────────────────────────────

class TestFxRates:
    def test_upsert_and_get(self, mock_conn):
        from src.database.repository import upsert_fx_rates, get_fx_rate
        upsert_fx_rates({"2024-01-01": 3.65, "2024-01-02": 3.70})
        assert get_fx_rate("2024-01-01") == pytest.approx(3.65)
        assert get_fx_rate("2024-01-02") == pytest.approx(3.70)

    def test_missing_date_returns_none(self, mock_conn):
        from src.database.repository import get_fx_rate
        assert get_fx_rate("2024-12-31") is None

    def test_get_all_fx_dates(self, mock_conn):
        from src.database.repository import upsert_fx_rates, get_all_fx_dates
        upsert_fx_rates({"2024-01-01": 3.65, "2024-01-02": 3.70})
        dates = get_all_fx_dates()
        assert dates == {"2024-01-01", "2024-01-02"}


# ── Metadata ──────────────────────────────────────────────────────────────────

class TestMetadata:
    def test_set_and_get(self, mock_conn):
        from src.database.repository import set_meta, get_meta
        set_meta("version", "2.0")
        assert get_meta("version") == "2.0"

    def test_upsert_overwrites(self, mock_conn):
        from src.database.repository import set_meta, get_meta
        set_meta("key", "old")
        set_meta("key", "new")
        assert get_meta("key") == "new"

    def test_missing_key_returns_none(self, mock_conn):
        from src.database.repository import get_meta
        assert get_meta("nonexistent") is None


# ── Realized Trades ───────────────────────────────────────────────────────────

class TestRealizedTrades:
    def test_insert_and_get(self, mock_conn):
        from src.database.repository import insert_realized_trade, get_realized_trades
        trade = {
            "date": "2024-01-01", "security_symbol": "12345",
            "security_name": "Test", "market": "TASE", "currency": "₪",
            "quantity_sold": 5, "avg_cost": 100, "sale_price": 120,
            "cost_total": 500, "proceeds": 600,
            "realized_pnl": 100, "realized_pnl_pct": 20.0,
        }
        insert_realized_trade(trade)
        rows = get_realized_trades()
        assert len(rows) == 1
        assert rows[0]["realized_pnl"] == pytest.approx(100.0)

    def test_clear(self, mock_conn):
        from src.database.repository import insert_realized_trade, clear_realized_trades, get_realized_trades
        trade = {
            "date": "2024-01-01", "security_symbol": "12345",
            "security_name": "Test", "market": "TASE", "currency": "₪",
            "quantity_sold": 5, "avg_cost": 100, "sale_price": 120,
            "cost_total": 500, "proceeds": 600,
            "realized_pnl": 100, "realized_pnl_pct": 20.0,
        }
        insert_realized_trade(trade)
        clear_realized_trades()
        assert len(get_realized_trades()) == 0


# ── Daily Portfolio State ─────────────────────────────────────────────────────

class TestDailyState:
    def test_upsert_and_get(self, mock_conn):
        from src.database.repository import upsert_daily_state, get_daily_portfolio_states
        state = {
            "date": "2024-01-01", "nis_invested": 10000, "nis_cash": 5000,
            "nis_total_cost": 15000, "usd_invested": 3000, "usd_cash": 1000,
            "usd_total_cost": 4000, "fx_rate": 3.7, "total_cost_nis": 29800,
            "cum_realized_pnl_nis": 500, "cum_realized_pnl_usd": 100,
        }
        upsert_daily_state(state)
        rows = get_daily_portfolio_states()
        assert len(rows) == 1
        assert rows[0]["total_cost_nis"] == pytest.approx(29800.0)

    def test_clear(self, mock_conn):
        from src.database.repository import upsert_daily_state, clear_daily_portfolio_state, get_daily_portfolio_states
        state = {
            "date": "2024-01-01", "nis_invested": 10000, "nis_cash": 5000,
            "nis_total_cost": 15000, "usd_invested": 0, "usd_cash": 0,
            "usd_total_cost": 0, "fx_rate": 3.7, "total_cost_nis": 15000,
            "cum_realized_pnl_nis": 0, "cum_realized_pnl_usd": 0,
        }
        upsert_daily_state(state)
        clear_daily_portfolio_state()
        assert len(get_daily_portfolio_states()) == 0


# ── Price Cache ───────────────────────────────────────────────────────────────

class TestPriceCache:
    def test_upsert_and_get(self, mock_conn):
        from src.database.repository import upsert_price, get_cached_price
        upsert_price("12345", "TASE", 170.0, "₪", "twelvedata", "2024-01-01")
        assert get_cached_price("12345", "TASE", "2024-01-01") == pytest.approx(170.0)

    def test_missing_returns_none(self, mock_conn):
        from src.database.repository import get_cached_price
        assert get_cached_price("NOEXIST", "TASE", "2024-01-01") is None


# ── Benchmark Cache ───────────────────────────────────────────────────────────

class TestBenchmarkCache:
    def test_upsert_and_get(self, mock_conn):
        from src.database.repository import upsert_benchmark_prices, get_benchmark_prices
        upsert_benchmark_prices("SPY", {"2024-01-01": 470.0, "2024-01-02": 472.5})
        prices = get_benchmark_prices("SPY")
        assert prices["2024-01-01"] == pytest.approx(470.0)
        assert prices["2024-01-02"] == pytest.approx(472.5)

    def test_date_range(self, mock_conn):
        from src.database.repository import upsert_benchmark_prices, get_benchmark_date_range
        upsert_benchmark_prices("SPY", {"2024-01-01": 470.0, "2024-06-30": 500.0})
        min_d, max_d = get_benchmark_date_range("SPY")
        assert min_d == "2024-01-01"
        assert max_d == "2024-06-30"

    def test_empty_returns_none(self, mock_conn):
        from src.database.repository import get_benchmark_date_range
        min_d, max_d = get_benchmark_date_range("NOEXIST")
        assert min_d is None
        assert max_d is None


# ── Snapshots ─────────────────────────────────────────────────────────────────

class TestSnapshots:
    def test_save_snapshot(self, mock_conn):
        from src.database.repository import save_snapshot
        summary = {
            "snapshot_date": "2024-01-01",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trigger": "test",
            "nis_stocks_value": 50000, "nis_cash": 10000, "nis_total": 60000,
            "usd_stocks_value": 5000, "usd_cash": 1000, "usd_total": 6000,
            "fx_rate": 3.7, "total_nis": 82200,
            "realized_pnl_nis": 500, "realized_pnl_usd": 100,
        }
        positions = [{
            "security_symbol": "12345", "security_name": "Test",
            "market": "TASE", "currency": "₪", "quantity": 100,
            "average_cost": 170, "total_invested": 17000,
            "total_invested_nis": 17000,
        }]
        snap_id = save_snapshot(summary, positions)
        assert snap_id > 0


# ── Import Log ────────────────────────────────────────────────────────────────

class TestImportLog:
    def test_log_and_get_last(self, mock_conn):
        from src.database.repository import log_import, get_last_import
        log_import("test.xlsx", 100, 90, 10)
        last = get_last_import()
        assert last["source_file"] == "test.xlsx"
        assert last["rows_new"] == 90


# ── TASE Symbol Map ──────────────────────────────────────────────────────────

class TestTaseSymbolMap:
    def test_upsert_and_get(self, mock_conn):
        from src.database.repository import upsert_tase_symbol, get_tase_symbol
        upsert_tase_symbol("445015", "MTRX:TLV", "MTRX.TA", "Matrix IT")
        result = get_tase_symbol("445015")
        assert result["td_symbol"] == "MTRX:TLV"
        assert result["yf_symbol"] == "MTRX.TA"

    def test_missing_returns_none(self, mock_conn):
        from src.database.repository import get_tase_symbol
        assert get_tase_symbol("NOEXIST") is None
