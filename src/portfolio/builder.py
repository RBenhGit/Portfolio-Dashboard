"""Portfolio builder — sequential pass over all classified transactions.

Produces:
  - nis_positions / usd_positions (current open holdings)
  - nis_cash / usd_cash (running cash balances)
  - daily_portfolio_state (per unique transaction date)
  - realized_trades (per sell)
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.database import repository
from src.market.price_fetcher import get_price
from src.market.symbol_mapper import is_option
from src.models.position import Position

logger = logging.getLogger(__name__)

_EPS = 0.001   # minimum quantity threshold


def _reorder_options_expiry(transactions: list) -> list:
    """Ensure option expiry credits (הפקדה פקיעה) are processed AFTER all
    removes on the same date, so that the short position already exists when
    the credit arrives to close it.

    Sort key tiers within a date:
      _10  regular adds   (buys, deposits)
      _11  regular removes  (sells, withdrawals)
      _12  option expiry credits  (הפקדה פקיעה)
    """
    def sort_key(tx):
        date = tx["date"]
        if tx["transaction_type"] == "הפקדה פקיעה":
            return date + "_12"
        dir_priority = "0" if tx.get("share_direction") == "add" else "1"
        return date + "_1" + dir_priority

    return sorted(transactions, key=sort_key)


_INITIAL_POS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "initial_positions.json"


def _load_initial_positions(
    positions_nis: dict[str, Position],
    positions_usd: dict[str, Position],
    transactions: list[dict],
) -> None:
    """Seed positions from config/initial_positions.json (pre-export holdings).

    These are shares acquired before the IBI Excel export period.  The config
    stores NIS cost basis; we derive USD cost using the FX rate on the earliest
    transaction date.
    """
    if not _INITIAL_POS_PATH.exists():
        return

    try:
        data = json.loads(_INITIAL_POS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read initial_positions.json: %s", exc)
        return

    entries = data.get("positions", [])
    if not entries:
        return

    # FX rate near the earliest transaction date (for NIS → USD conversion).
    # The exact date may be a weekend/holiday, so scan the first few dates.
    fx_rate = None
    seen_dates = dict.fromkeys(tx["date"] for tx in transactions[:50])
    for d in seen_dates:
        fx_rate = repository.get_fx_rate(d)
        if fx_rate is not None:
            break

    for entry in entries:
        sym = entry["symbol"]
        currency = entry.get("currency", "$")
        positions = positions_nis if currency == "₪" else positions_usd
        cost_nis = entry["cost_basis_nis"]

        if currency == "$" and fx_rate:
            cost_usd = cost_nis / fx_rate
        else:
            cost_usd = cost_nis  # NIS positions: cost is already in NIS

        pos = Position(
            security_symbol=sym,
            security_name=entry.get("security_name"),
            market=entry.get("market", "US"),
            currency=currency,
            quantity=entry["quantity"],
            total_invested=cost_usd if currency == "$" else cost_nis,
            total_invested_nis=cost_nis,
        )
        positions[sym] = pos
        logger.info(
            "Seeded pre-export position: %s qty=%.2f cost=%s%.2f (NIS %.2f)",
            sym, pos.quantity, currency, pos.total_invested, cost_nis,
        )


def build(trigger: str = "startup") -> dict:
    """Run the full sequential portfolio build.

    Returns a summary dict with current positions and cash.
    Also writes daily_portfolio_state and realized_trades to DB.
    """
    rows = repository.get_all_transactions(include_phantom=True)
    if not rows:
        logger.info("No transactions in DB — nothing to build.")
        return _empty_summary()

    transactions = [dict(r) for r in rows]
    transactions = _reorder_options_expiry(transactions)

    # State
    positions_nis: dict[str, Position] = {}
    positions_usd: dict[str, Position] = {}
    nis_cash = 0.0
    usd_cash = 0.0
    cum_realized_pnl_nis = 0.0
    cum_realized_pnl_usd = 0.0
    current_date: str | None = None

    # Seed pre-export holdings (shares acquired before the IBI Excel period)
    _load_initial_positions(positions_nis, positions_usd, transactions)

    # Clear tables we recompute fully
    repository.clear_daily_portfolio_state()
    repository.clear_realized_trades()

    def _record_state(date: str) -> None:
        nis_inv = sum(p.total_invested for p in positions_nis.values())
        usd_inv = sum(p.total_invested for p in positions_usd.values())
        fx = repository.get_fx_rate(date) or 3.7   # fallback rate

        # Compute market values from closing prices
        nis_mv = 0.0
        for sym, pos in positions_nis.items():
            px = get_price(sym, pos.market, pos.security_name, date)
            if px is not None:
                nis_mv += px * pos.quantity

        usd_mv = 0.0
        for sym, pos in positions_usd.items():
            px = get_price(sym, pos.market, pos.security_name, date)
            if px is not None:
                usd_mv += px * pos.quantity

        repository.upsert_daily_state({
            "date":                date,
            "nis_invested":        nis_inv,
            "nis_cash":            nis_cash,
            "nis_total_cost":      nis_inv + nis_cash,
            "usd_invested":        usd_inv,
            "usd_cash":            usd_cash,
            "usd_total_cost":      usd_inv + usd_cash,
            "fx_rate":             fx,
            "total_cost_nis":      (nis_inv + nis_cash) + (usd_inv + usd_cash) * fx,
            "cum_realized_pnl_nis": cum_realized_pnl_nis,
            "cum_realized_pnl_usd": cum_realized_pnl_usd,
            "nis_market_value":       nis_mv,
            "usd_market_value":       usd_mv,
            "total_market_value_nis": (nis_mv + nis_cash) + (usd_mv + usd_cash) * fx,
        })

    for tx in transactions:
        date = tx["date"]

        # ── Date boundary: record state before processing first tx of new date ──
        if date != current_date and current_date is not None:
            _record_state(current_date)
        current_date = date

        # ── NIS cash: use IBI's own running balance column (יתרה שקלית) ─────────
        # This avoids reconstructing from a missing initial balance.
        bal = tx.get("balance")
        if bal is not None and float(bal or 0) != 0:
            nis_cash = float(bal)
        # ── USD cash: accumulated from USD cash flows ─────────────────────────
        usd_cash += float(tx.get("cash_flow_usd") or 0)

        # Skip phantoms and non-share transactions
        if tx.get("is_phantom") or tx.get("share_direction") == "none":
            continue

        # Select the right position map
        currency = str(tx.get("currency") or "").strip()
        positions = positions_nis if currency == "₪" else positions_usd
        sym  = str(tx.get("security_symbol") or "")
        name = tx.get("security_name")
        mkt  = tx.get("market") or ("TASE" if currency == "₪" else "US")

        effect    = tx.get("effect", "none")
        direction = tx.get("share_direction", "none")
        qty_abs   = float(tx.get("share_quantity_abs") or 0)
        exec_p    = float(tx.get("execution_price") or 0)
        cost_b    = float(tx.get("cost_basis") or 0)
        cost_b_nis = float(tx.get("cost_basis_nis") or cost_b)  # fallback for NIS

        if direction == "none" or qty_abs == 0:
            continue

        # Get or create position
        if sym not in positions:
            positions[sym] = Position(
                security_symbol=sym,
                security_name=name,
                market=mkt,
                currency=currency,
            )
        pos = positions[sym]

        if direction == "add":
            # BUY / DEPOSIT / BONUS / SPLIT-ADD
            if effect == "option_expiry" and pos.quantity > -_EPS:
                # Expiry credit for an option whose original sell is not in our
                # data (sold before the reporting period).  Skip to avoid
                # creating a phantom LONG position.
                logger.debug(
                    "Skipping orphan option expiry credit %s qty=%.4f on %s "
                    "(no prior short position)", sym, qty_abs, date,
                )
                continue
            elif effect == "stock_split":
                # Split: ratio = new_qty / current_qty → revalue avg_cost
                if pos.quantity > _EPS:
                    ratio = (pos.quantity + qty_abs) / pos.quantity
                    pos.quantity = pos.quantity * ratio
                    # total_invested unchanged; avg_cost drops automatically
                    # avg_cost is computed as total_invested / quantity
                else:
                    pos.quantity += qty_abs
            else:
                pos.quantity += qty_abs
                pos.total_invested += cost_b
                pos.total_invested_nis += cost_b_nis

        elif direction == "remove":
            # SELL / WITHDRAWAL
            if pos.quantity < qty_abs - _EPS:
                if is_option(sym, name):
                    # Options can be sold short (written) — allow negative position
                    logger.debug(
                        "Option short sell %s: have %.4f, selling %.4f on %s",
                        sym, pos.quantity, qty_abs, date
                    )
                else:
                    # Pre-transfer position: shares bought before data starts
                    shortfall = qty_abs - pos.quantity
                    logger.info(
                        "Pre-transfer adjustment for %s: adding %.4f phantom shares "
                        "(have %.4f, need %.4f on %s)",
                        sym, shortfall, pos.quantity, qty_abs, date
                    )
                    pos.quantity += shortfall  # fill gap so sell proceeds normally

            realized = qty_abs * (exec_p - pos.average_cost)
            repository.insert_realized_trade({
                "date":            date,
                "security_symbol": sym,
                "security_name":   name,
                "market":          mkt,
                "currency":        currency,
                "quantity_sold":   qty_abs,
                "avg_cost":        pos.average_cost,
                "sale_price":      exec_p,
                "cost_total":      qty_abs * pos.average_cost,
                "proceeds":        qty_abs * exec_p,
                "realized_pnl":    realized,
                "realized_pnl_pct": (
                    realized / (qty_abs * pos.average_cost) * 100
                    if pos.average_cost > 0 else 0.0
                ),
            })

            if currency == "₪":
                cum_realized_pnl_nis += realized
            else:
                cum_realized_pnl_usd += realized

            reduce_factor = qty_abs / pos.quantity if pos.quantity > 0 else 1.0
            pos.quantity          -= qty_abs
            pos.total_invested    *= (1 - reduce_factor)
            pos.total_invested_nis *= (1 - reduce_factor)

            # Options can go negative (short positions) — only delete non-options
            if pos.quantity < _EPS and not is_option(sym, name):
                del positions[sym]

    # Record final date
    if current_date:
        _record_state(current_date)

    # Extract option positions — keep ALL (including closed with qty ≈ 0)
    # so the UI can offer an "All / Open only" toggle.
    options_nis = {
        k: v for k, v in positions_nis.items()
        if is_option(k, v.security_name)
    }
    options_usd = {
        k: v for k, v in positions_usd.items()
        if is_option(k, v.security_name)
    }

    # Filter: keep only real non-option positions with positive quantity
    positions_nis = {
        k: v for k, v in positions_nis.items()
        if v.quantity > _EPS and not is_option(k, v.security_name)
    }
    positions_usd = {
        k: v for k, v in positions_usd.items()
        if v.quantity > _EPS and not is_option(k, v.security_name)
    }

    result = {
        "positions_nis": positions_nis,
        "positions_usd": positions_usd,
        "options_nis": options_nis,
        "options_usd": options_usd,
        "nis_cash": nis_cash,
        "usd_cash": usd_cash,
        "cum_realized_pnl_nis": cum_realized_pnl_nis,
        "cum_realized_pnl_usd": cum_realized_pnl_usd,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    repository.save_portfolio_current(result)
    return result


def _empty_summary() -> dict:
    return {
        "positions_nis": {},
        "positions_usd": {},
        "options_nis": {},
        "options_usd": {},
        "nis_cash": 0.0,
        "usd_cash": 0.0,
        "cum_realized_pnl_nis": 0.0,
        "cum_realized_pnl_usd": 0.0,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
