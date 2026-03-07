"""All database CRUD operations."""
import json
import sqlite3
from datetime import datetime, timezone
from src.database.db import get_connection
from src.models.position import Position


# ── Transactions ──────────────────────────────────────────────────────────────

_TX_COLS = [
    "date", "transaction_type", "effect", "is_phantom",
    "security_name", "security_symbol", "market", "currency",
    "quantity", "share_direction", "share_quantity_abs",
    "execution_price_raw", "execution_price",
    "commission", "additional_fees",
    "amount_foreign_currency", "amount_local_currency",
    "balance", "capital_gains_tax_estimate",
    "cost_basis", "cash_flow_nis", "cash_flow_usd",
    "fx_rate_on_date", "cost_basis_nis", "row_hash",
]


def insert_transactions_deduped(transactions: list[dict]) -> tuple[int, int]:
    """Insert classified transactions; skip duplicates by row_hash.
    Returns (rows_new, rows_duplicate).
    """
    if not transactions:
        return 0, 0
    placeholders = ", ".join("?" * len(_TX_COLS))
    sql = (
        f"INSERT OR IGNORE INTO transactions ({', '.join(_TX_COLS)}) "
        f"VALUES ({placeholders})"
    )
    conn = get_connection()
    rows_new = rows_dup = 0
    with conn:
        for tx in transactions:
            values = [tx.get(c) for c in _TX_COLS]
            cur = conn.execute(sql, values)
            if cur.rowcount:
                rows_new += 1
            else:
                rows_dup += 1
    conn.close()
    return rows_new, rows_dup


def get_max_transaction_date() -> str | None:
    """Return the latest transaction date (YYYY-MM-DD) or None if no transactions."""
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(date) AS max_date FROM transactions WHERE is_phantom=0"
    ).fetchone()
    conn.close()
    return row["max_date"] if row and row["max_date"] else None


def get_all_transactions(include_phantom: bool = False) -> list[sqlite3.Row]:
    conn = get_connection()
    sql = "SELECT * FROM transactions ORDER BY date ASC"
    if not include_phantom:
        sql = "SELECT * FROM transactions WHERE is_phantom=0 ORDER BY date ASC"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def get_transaction_count() -> int:
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    return n


# ── FX Rates ──────────────────────────────────────────────────────────────────

def upsert_fx_rates(rates: dict[str, float], source: str = "twelvedata") -> None:
    conn = get_connection()
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO fx_rates (date, usd_ils, source) VALUES (?,?,?)",
            [(d, r, source) for d, r in rates.items()],
        )
    conn.close()


def get_fx_rate(date: str) -> float | None:
    conn = get_connection()
    row = conn.execute("SELECT usd_ils FROM fx_rates WHERE date=?", (date,)).fetchone()
    conn.close()
    return float(row["usd_ils"]) if row else None


def get_all_fx_dates() -> set[str]:
    conn = get_connection()
    rows = conn.execute("SELECT date FROM fx_rates").fetchall()
    conn.close()
    return {r["date"] for r in rows}


def get_transaction_dates() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT date FROM transactions ORDER BY date"
    ).fetchall()
    conn.close()
    return [r["date"] for r in rows]


# ── Price cache ───────────────────────────────────────────────────────────────

def upsert_price(symbol: str, market: str, price: float,
                 currency: str, source: str, price_date: str = "") -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO price_cache "
            "(symbol, market, price_date, price, currency, fetched_at, source) "
            "VALUES (?,?,?,?,?,?,?)",
            (symbol, market, price_date, price, currency,
             datetime.now(timezone.utc).isoformat(), source),
        )
    conn.close()


def get_cached_price(symbol: str, market: str, price_date: str = "") -> float | None:
    """Return cached closing price for (symbol, market, price_date) or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT price FROM price_cache WHERE symbol=? AND market=? AND price_date=?",
        (symbol, market, price_date),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return float(row["price"])


# ── Metadata ──────────────────────────────────────────────────────────────────

def set_meta(key: str, value: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?,?)", (key, value)
        )
    conn.close()


def get_meta(key: str) -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


# ── Realized trades ───────────────────────────────────────────────────────────

def insert_realized_trade(trade: dict) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO realized_trades "
            "(date, security_symbol, security_name, market, currency, "
            "quantity_sold, avg_cost, sale_price, cost_total, "
            "proceeds, realized_pnl, realized_pnl_pct) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (trade["date"], trade["security_symbol"], trade.get("security_name"),
             trade.get("market"), trade.get("currency"),
             trade["quantity_sold"], trade["avg_cost"], trade["sale_price"],
             trade["cost_total"], trade["proceeds"],
             trade["realized_pnl"], trade["realized_pnl_pct"]),
        )
    conn.close()


def clear_realized_trades() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM realized_trades")
    conn.close()


def get_realized_trades() -> list[sqlite3.Row]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM realized_trades ORDER BY date ASC").fetchall()
    conn.close()
    return rows


# ── Daily portfolio state ─────────────────────────────────────────────────────

def upsert_daily_state(state: dict) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO daily_portfolio_state "
            "(date, nis_invested, nis_cash, nis_total_cost, "
            "usd_invested, usd_cash, usd_total_cost, "
            "fx_rate, total_cost_nis, cum_realized_pnl_nis, cum_realized_pnl_usd, "
            "nis_market_value, usd_market_value, total_market_value_nis) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (state["date"],
             state.get("nis_invested"), state.get("nis_cash"), state.get("nis_total_cost"),
             state.get("usd_invested"), state.get("usd_cash"), state.get("usd_total_cost"),
             state.get("fx_rate"), state.get("total_cost_nis"),
             state.get("cum_realized_pnl_nis"), state.get("cum_realized_pnl_usd"),
             state.get("nis_market_value"), state.get("usd_market_value"),
             state.get("total_market_value_nis")),
        )
    conn.close()


def clear_daily_portfolio_state() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM daily_portfolio_state")
    conn.close()


def get_daily_portfolio_states() -> list[sqlite3.Row]:
    """Return all daily_portfolio_state rows ordered by date."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM daily_portfolio_state ORDER BY date ASC"
    ).fetchall()
    conn.close()
    return rows


# ── Benchmark cache ──────────────────────────────────────────────────────────

def upsert_benchmark_prices(symbol: str, prices: dict[str, float]) -> None:
    """Cache benchmark daily closes. prices = {date_str: close_price}."""
    if not prices:
        return
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO benchmark_cache "
            "(symbol, date, close, fetched_at) VALUES (?,?,?,?)",
            [(symbol, d, p, now) for d, p in prices.items()],
        )
    conn.close()


def get_benchmark_prices(symbol: str) -> dict[str, float]:
    """Return {date: close} for a cached benchmark."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT date, close FROM benchmark_cache WHERE symbol=? ORDER BY date",
        (symbol,),
    ).fetchall()
    conn.close()
    return {r["date"]: r["close"] for r in rows}


def get_benchmark_date_range(symbol: str) -> tuple[str | None, str | None]:
    """Return (min_date, max_date) for cached benchmark data."""
    conn = get_connection()
    row = conn.execute(
        "SELECT MIN(date) as min_d, MAX(date) as max_d "
        "FROM benchmark_cache WHERE symbol=?",
        (symbol,),
    ).fetchone()
    conn.close()
    if row and row["min_d"]:
        return row["min_d"], row["max_d"]
    return None, None


# ── Snapshots ─────────────────────────────────────────────────────────────────

def save_snapshot(summary: dict, positions: list[dict]) -> int:
    conn = get_connection()
    with conn:
        cur = conn.execute(
            "INSERT INTO portfolio_snapshots "
            "(snapshot_date, created_at, trigger, "
            "nis_stocks_value, nis_cash, nis_total, "
            "usd_stocks_value, usd_cash, usd_total, "
            "fx_rate, total_nis, realized_pnl_nis, realized_pnl_usd) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (summary["snapshot_date"], summary["created_at"], summary["trigger"],
             summary.get("nis_stocks_value"), summary.get("nis_cash"), summary.get("nis_total"),
             summary.get("usd_stocks_value"), summary.get("usd_cash"), summary.get("usd_total"),
             summary.get("fx_rate"), summary.get("total_nis"),
             summary.get("realized_pnl_nis"), summary.get("realized_pnl_usd")),
        )
        snap_id = cur.lastrowid
        if positions:
            conn.executemany(
                "INSERT INTO position_snapshots "
                "(snapshot_id, security_symbol, security_name, market, currency, "
                "quantity, average_cost, total_invested, total_invested_nis, "
                "market_price, market_value, unrealized_pnl, unrealized_pnl_pct) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(snap_id, p["security_symbol"], p.get("security_name"),
                  p.get("market"), p.get("currency"),
                  p["quantity"], p["average_cost"],
                  p["total_invested"], p.get("total_invested_nis"),
                  p.get("market_price"), p.get("market_value"),
                  p.get("unrealized_pnl"), p.get("unrealized_pnl_pct"))
                 for p in positions],
            )
    conn.close()
    return snap_id


def log_import(source_file: str, rows_total: int,
               rows_new: int, rows_duplicate: int) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO import_log "
            "(imported_at, source_file, rows_total, rows_new, rows_duplicate) "
            "VALUES (?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(),
             source_file, rows_total, rows_new, rows_duplicate),
        )
    conn.close()


def get_last_import() -> sqlite3.Row | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM import_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row


# ── TASE symbol map ──────────────────────────────────────────────────────────

def get_tase_symbol(ibi_id: str) -> dict | None:
    """Return cached TASE symbol mapping or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT td_symbol, yf_symbol, name FROM tase_symbol_map WHERE ibi_id=?",
        (ibi_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"td_symbol": row["td_symbol"], "yf_symbol": row["yf_symbol"], "name": row["name"]}


def upsert_tase_symbol(ibi_id: str, td_symbol: str, yf_symbol: str, name: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO tase_symbol_map "
            "(ibi_id, td_symbol, yf_symbol, name, updated_at) VALUES (?,?,?,?,?)",
            (ibi_id, td_symbol, yf_symbol, name,
             datetime.now(timezone.utc).isoformat()),
        )
    conn.close()


# ── Portfolio current (fast-load cache) ──────────────────────────────────────

def save_portfolio_current(result: dict) -> None:
    """Persist the build() result dict to DB for fast reload."""
    # Serialize Position objects to dicts
    serializable = {}
    for key in ("positions_nis", "positions_usd", "options_nis", "options_usd"):
        positions = result.get(key, {})
        serializable[key] = {
            sym: pos.to_snapshot_dict() if isinstance(pos, Position) else pos
            for sym, pos in positions.items()
        }
    for key in ("nis_cash", "usd_cash", "cum_realized_pnl_nis",
                "cum_realized_pnl_usd", "built_at"):
        serializable[key] = result.get(key)

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO portfolio_current (key, value) VALUES (?,?)",
            ("portfolio", json.dumps(serializable)),
        )
    conn.close()


def load_portfolio_current() -> dict | None:
    """Load the cached build() result from DB. Returns None if not available."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM portfolio_current WHERE key='portfolio'"
    ).fetchone()
    conn.close()
    if not row:
        return None

    data = json.loads(row["value"])

    # Reconstruct Position objects from dicts
    for key in ("positions_nis", "positions_usd", "options_nis", "options_usd"):
        if key in data and isinstance(data[key], dict):
            data[key] = {
                sym: Position.from_dict(d) for sym, d in data[key].items()
            }
    return data


def is_portfolio_stale() -> bool:
    """Check if cached portfolio is outdated (new import since last build)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM portfolio_current WHERE key='portfolio'"
    ).fetchone()
    if not row:
        conn.close()
        return True

    data = json.loads(row["value"])
    built_at = data.get("built_at")
    if not built_at:
        conn.close()
        return True

    import_row = conn.execute(
        "SELECT imported_at FROM import_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not import_row:
        return False  # no imports ever → cached data is valid

    return import_row["imported_at"] > built_at
