"""SQLite database connection and schema creation."""
import sqlite3
from src.config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Return a WAL-mode connection with row_factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_schema() -> None:
    """Create all 11 tables if they don't exist."""
    conn = get_connection()
    with conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS transactions (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    date                       TEXT NOT NULL,
    transaction_type           TEXT NOT NULL,
    effect                     TEXT NOT NULL,
    is_phantom                 INTEGER NOT NULL DEFAULT 0,
    security_name              TEXT,
    security_symbol            TEXT,
    market                     TEXT,
    currency                   TEXT,
    quantity                   REAL,
    share_direction            TEXT,
    share_quantity_abs         REAL,
    execution_price_raw        REAL,
    execution_price            REAL,
    commission                 REAL,
    additional_fees            REAL,
    amount_foreign_currency    REAL,
    amount_local_currency      REAL,
    balance                    REAL,
    capital_gains_tax_estimate REAL,
    cost_basis                 REAL,
    cash_flow_nis              REAL,
    cash_flow_usd              REAL,
    fx_rate_on_date            REAL,
    cost_basis_nis             REAL,
    row_hash                   TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS fx_rates (
    date        TEXT PRIMARY KEY,
    usd_ils     REAL NOT NULL,
    source      TEXT
);

CREATE TABLE IF NOT EXISTS price_cache (
    symbol      TEXT NOT NULL,
    market      TEXT NOT NULL,
    price_date  TEXT NOT NULL,
    price       REAL NOT NULL,
    currency    TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    source      TEXT,
    PRIMARY KEY (symbol, market, price_date)
);

CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date     TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    trigger           TEXT NOT NULL,
    nis_stocks_value  REAL,
    nis_cash          REAL,
    nis_total         REAL,
    usd_stocks_value  REAL,
    usd_cash          REAL,
    usd_total         REAL,
    fx_rate           REAL,
    total_nis         REAL,
    realized_pnl_nis  REAL,
    realized_pnl_usd  REAL
);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id        INTEGER NOT NULL REFERENCES portfolio_snapshots(id),
    security_symbol    TEXT NOT NULL,
    security_name      TEXT,
    market             TEXT,
    currency           TEXT,
    quantity           REAL,
    average_cost       REAL,
    total_invested     REAL,
    total_invested_nis REAL,
    market_price       REAL,
    market_value       REAL,
    unrealized_pnl     REAL,
    unrealized_pnl_pct REAL
);

CREATE TABLE IF NOT EXISTS daily_portfolio_state (
    date                 TEXT PRIMARY KEY,
    nis_invested         REAL,
    nis_cash             REAL,
    nis_total_cost       REAL,
    usd_invested         REAL,
    usd_cash             REAL,
    usd_total_cost       REAL,
    fx_rate              REAL,
    total_cost_nis       REAL,
    cum_realized_pnl_nis REAL,
    cum_realized_pnl_usd REAL,
    nis_market_value     REAL,
    usd_market_value     REAL,
    total_market_value_nis REAL
);

CREATE TABLE IF NOT EXISTS realized_trades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,
    security_symbol  TEXT NOT NULL,
    security_name    TEXT,
    market           TEXT,
    currency         TEXT,
    quantity_sold    REAL,
    avg_cost         REAL,
    sale_price       REAL,
    cost_total       REAL,
    proceeds         REAL,
    realized_pnl     REAL,
    realized_pnl_pct REAL
);

CREATE TABLE IF NOT EXISTS import_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at    TEXT NOT NULL,
    source_file    TEXT NOT NULL,
    rows_total     INTEGER,
    rows_new       INTEGER,
    rows_duplicate INTEGER
);

CREATE TABLE IF NOT EXISTS tase_symbol_map (
    ibi_id      TEXT PRIMARY KEY,
    td_symbol   TEXT,
    yf_symbol   TEXT,
    name        TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_cache (
    symbol     TEXT NOT NULL,
    date       TEXT NOT NULL,
    close      REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (symbol, date)
);
        """)

    # ── Migrations ────────────────────────────────────────────────────────────
    # price_cache: add price_date column and migrate to new PK
    cols = {r[1] for r in conn.execute("PRAGMA table_info(price_cache)").fetchall()}
    if "price_date" not in cols:
        conn.executescript("""
            DROP TABLE IF EXISTS price_cache;
            CREATE TABLE price_cache (
                symbol      TEXT NOT NULL,
                market      TEXT NOT NULL,
                price_date  TEXT NOT NULL,
                price       REAL NOT NULL,
                currency    TEXT NOT NULL,
                fetched_at  TEXT NOT NULL,
                source      TEXT,
                PRIMARY KEY (symbol, market, price_date)
            );
        """)

    # daily_portfolio_state: add market value columns
    dps_cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_portfolio_state)").fetchall()}
    if "nis_market_value" not in dps_cols:
        conn.execute("ALTER TABLE daily_portfolio_state ADD COLUMN nis_market_value REAL")
        conn.execute("ALTER TABLE daily_portfolio_state ADD COLUMN usd_market_value REAL")
        conn.execute("ALTER TABLE daily_portfolio_state ADD COLUMN total_market_value_nis REAL")

    conn.close()
