"""Portfolio builder — sequential pass over all classified transactions.

Produces:
  - nis_positions / usd_positions (current open holdings)
  - nis_cash / usd_cash (running cash balances)
  - daily_portfolio_state (per unique transaction date)
  - realized_trades (per sell)
"""
import logging
from datetime import datetime, timezone

from src.database import repository
from src.market.symbol_mapper import is_option
from src.models.position import Position

logger = logging.getLogger(__name__)

_EPS = 0.001   # minimum quantity threshold


def _reorder_options_expiry(transactions: list) -> list:
    """Fix IBI ordering bug: הפקדה פקיעה (expiry credit) is recorded AFTER
    the sell (מכירה מעוף) of the same option. This causes an 'insufficient shares'
    error during the sequential pass.

    Fix: for 8-digit option symbols (starting 8x/9x), move any הפקדה פקיעה
    deposit to one day *before* the earliest sell of that symbol.
    We do this by adjusting the sort key only — not the stored date.
    """
    # Build map: option_symbol → earliest sell date
    sell_dates: dict[str, str] = {}
    for tx in transactions:
        sym = str(tx["security_symbol"] or "")
        if (tx["effect"] in ("sell", "option_expiry") and
                tx["share_direction"] == "remove" and
                len(sym) == 8 and sym[:1] in ("8", "9")):
            if sym not in sell_dates or tx["date"] < sell_dates[sym]:
                sell_dates[sym] = tx["date"]

    def sort_key(tx):
        sym = str(tx["security_symbol"] or "")
        if (tx["transaction_type"] == "הפקדה פקיעה" and
                sym in sell_dates):
            # Sort just before the sell date
            d = sell_dates[sym]
            return d + "_0"   # sorts before same date + "_1"
        # Within the same date, process adds before removes
        dir_priority = "0" if tx.get("share_direction") == "add" else "1"
        return tx["date"] + "_1" + dir_priority

    return sorted(transactions, key=sort_key)


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

    # Clear tables we recompute fully
    repository.clear_daily_portfolio_state()
    repository.clear_realized_trades()

    def _record_state(date: str) -> None:
        nis_inv = sum(p.total_invested for p in positions_nis.values())
        usd_inv = sum(p.total_invested for p in positions_usd.values())
        fx = repository.get_fx_rate(date) or 3.7   # fallback rate
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
            if effect == "stock_split":
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

    # Extract option positions (any with non-zero quantity, including short/negative)
    options_nis = {
        k: v for k, v in positions_nis.items()
        if is_option(k, v.security_name) and abs(v.quantity) > _EPS
    }
    options_usd = {
        k: v for k, v in positions_usd.items()
        if is_option(k, v.security_name) and abs(v.quantity) > _EPS
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

    return {
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
