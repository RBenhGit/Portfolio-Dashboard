"""IBI broker transaction classifier — all 21 transaction types."""
import re
from src.classifiers.base_classifier import BaseClassifier

_PHANTOM_SYMBOL_PREFIXES = ("999",)
_PHANTOM_SYMBOLS = {"99028", "5039813"}
_PHANTOM_NAME_KEYWORDS = (
    "מס לשלם", "מס ששולם", "מס תקבולים",
    "הכנס/תשלום מעוף", "הכנס תשלום מעוף",
)

_US_TICKER_RE = re.compile(r'^[A-Z]{1,6}$')
_TASE_NUMERIC_RE = re.compile(r'^\d{5,8}$')
_OPTION_RE = re.compile(r'^[89]\d{7}$')


class IBIClassifier(BaseClassifier):
    """Classify all 21 IBI transaction types."""

    def detect_phantom(self, row: dict) -> bool:
        sym  = str(row.get("security_symbol", "")).strip()
        name = str(row.get("security_name", "")).strip()
        if sym in _PHANTOM_SYMBOLS:
            return True
        if any(sym.startswith(p) for p in _PHANTOM_SYMBOL_PREFIXES):
            return True
        if any(kw in name for kw in _PHANTOM_NAME_KEYWORDS):
            return True
        return False

    def _detect_market(self, row: dict) -> str:
        currency = str(row.get("currency", "")).strip()
        sym      = str(row.get("security_symbol", "")).strip()
        if currency == "$":
            return "US"
        if currency == "₪" and _US_TICKER_RE.match(sym):
            return "US"   # dual-listed ETF/ADR on TASE
        if _TASE_NUMERIC_RE.match(sym):
            return "TASE"
        return "TASE"

    def classify(self, row: dict) -> dict:  # noqa: C901  (complex but intentional)
        tx_type   = str(row.get("transaction_type", "")).strip()
        currency  = str(row.get("currency", "")).strip()
        sym       = str(row.get("security_symbol", "")).strip()
        raw_price = float(row.get("execution_price_raw") or 0)
        qty       = float(row.get("quantity") or 0)
        amount_fc = float(row.get("amount_foreign_currency") or 0)
        amount_lc = float(row.get("amount_local_currency") or 0)
        comm      = float(row.get("commission") or 0)
        add_fees  = float(row.get("additional_fees") or 0)

        is_phantom  = self.detect_phantom(row)
        market      = self._detect_market(row)
        exec_price  = self.normalize_price(raw_price, currency)

        effect             = "none"
        share_direction    = "none"
        share_quantity_abs = 0.0
        cash_flow_nis      = 0.0
        cash_flow_usd      = 0.0
        cost_basis         = 0.0

        # ── NIS BUYS ─────────────────────────────────────────────────────────
        if tx_type in ("קניה שח", "קניה רצף", "קניה מעוף"):
            if sym == "99028":
                # Special case: NIS → USD forex conversion
                # IBI records this as "קניה שח" with symbol 99028
                # qty = USD amount received; amount_lc = NIS paid (negative)
                effect        = "forex_buy"
                is_phantom    = True
                cash_flow_nis = amount_lc        # negative (NIS out)
                cash_flow_usd = qty              # positive (USD in)
            elif not is_phantom:
                effect             = "buy"
                share_direction    = "add"
                share_quantity_abs = abs(qty)
                cost_basis         = abs(amount_lc)
                cash_flow_nis      = amount_lc   # negative

        # ── USD BUY ──────────────────────────────────────────────────────────
        elif tx_type == "קניה חול מטח":
            effect             = "buy"
            share_direction    = "add"
            share_quantity_abs = abs(qty)
            cost_basis         = abs(amount_fc)
            cash_flow_usd      = amount_fc            # negative

        # ── NIS SELLS ────────────────────────────────────────────────────────
        elif tx_type in ("מכירה שח", "מכירה רצף", "מכירה מעוף"):
            if not is_phantom:
                effect             = "sell"
                share_direction    = "remove"
                share_quantity_abs = abs(qty)         # IBI qty positive for sells
                cash_flow_nis      = abs(amount_lc)   # positive (cash in)

        # ── USD SELL ─────────────────────────────────────────────────────────
        elif tx_type == "מכירה חול מטח":
            effect             = "sell"
            share_direction    = "remove"
            share_quantity_abs = abs(qty)
            cash_flow_usd      = abs(amount_fc)       # positive (cash in)

        # ── DEPOSIT (shares in) ───────────────────────────────────────────────
        elif tx_type == "הפקדה":
            if not is_phantom:
                effect             = "deposit"
                share_direction    = "add" if qty > 0 else "remove"
                share_quantity_abs = abs(qty)
                cost_basis         = share_quantity_abs * exec_price

        # ── OPTION EXPIRY CREDIT ──────────────────────────────────────────────
        elif tx_type == "הפקדה פקיעה":
            if not is_phantom:
                effect             = "option_expiry"
                share_direction    = "add"
                share_quantity_abs = abs(qty)

        # ── WITHDRAWAL (shares out) ───────────────────────────────────────────
        elif tx_type == "משיכה":
            if not is_phantom:
                effect             = "withdrawal"
                share_direction    = "remove"
                share_quantity_abs = abs(qty)

        # ── OPTION EXPIRY DEBIT ───────────────────────────────────────────────
        elif tx_type == "משיכה פקיעה":
            effect             = "option_expiry"
            share_direction    = "remove"
            share_quantity_abs = abs(qty)

        # ── BONUS SHARES / STOCK SPLIT ────────────────────────────────────────
        elif tx_type == "הטבה":
            if raw_price == 0:
                # Zero price → likely stock split; builder will apply ratio
                effect             = "stock_split"
                share_direction    = "add"
                share_quantity_abs = abs(qty)
            else:
                # Positive price → bonus shares at 0 cost basis
                effect             = "bonus_or_split"
                share_direction    = "add"
                share_quantity_abs = abs(qty)
                cost_basis         = 0.0

        # ── USD DIVIDEND (99028 symbol) ───────────────────────────────────────
        elif tx_type == "הפקדה דיבידנד מטח":
            effect        = "dividend"
            cash_flow_usd = abs(amount_fc)
            is_phantom    = True   # symbol 99028 — not a real stock position

        # ── NIS DIVIDEND ──────────────────────────────────────────────────────
        elif tx_type == "דיבדנד":
            effect        = "dividend"
            cash_flow_nis = abs(amount_lc)

        # ── NIS INTEREST ──────────────────────────────────────────────────────
        elif tx_type == "ריבית מזומן בשח":
            effect        = "interest"
            cash_flow_nis = abs(amount_lc)

        # ── FOREIGN INTEREST TAX (phantom) ────────────────────────────────────
        elif tx_type == "משיכת ריבית מטח":
            effect        = "interest_tax"
            is_phantom    = True
            cash_flow_usd = amount_fc   # negative

        # ── FOREIGN TAXES (phantom) ───────────────────────────────────────────
        elif tx_type in ("משיכת מס חול מטח", "משיכת מס מטח"):
            effect        = "tax"
            is_phantom    = True
            cash_flow_usd = amount_fc   # negative

        # ── NIS CASH TRANSFER ─────────────────────────────────────────────────
        elif tx_type == "העברה מזומן בשח":
            effect        = "transfer"
            cash_flow_nis = amount_lc   # signed

        # ── NIS FEE ───────────────────────────────────────────────────────────
        elif tx_type == "דמי טפול מזומן בשח":
            effect        = "fee"
            cash_flow_nis = amount_lc   # negative

        return {
            "date":                       row.get("date"),
            "transaction_type":           tx_type,
            "security_name":              str(row.get("security_name", "")).strip() or None,
            "security_symbol":            sym or None,
            "currency":                   currency or None,
            "quantity":                   qty,
            "execution_price_raw":        raw_price,
            "commission":                 comm,
            "additional_fees":            add_fees,
            "amount_foreign_currency":    amount_fc,
            "amount_local_currency":      amount_lc,
            "balance":                    float(row.get("balance") or 0),
            "capital_gains_tax_estimate": float(row.get("capital_gains_tax_estimate") or 0),
            "row_hash":                   row.get("row_hash"),
            # Classified
            "effect":             effect,
            "is_phantom":         is_phantom,
            "market":             market,
            "execution_price":    exec_price,
            "share_direction":    share_direction,
            "share_quantity_abs": share_quantity_abs,
            "cost_basis":         cost_basis,
            "cash_flow_nis":      cash_flow_nis,
            "cash_flow_usd":      cash_flow_usd,
            # Filled by ingestion pipeline after FX fetch
            "fx_rate_on_date": None,
            "cost_basis_nis":  None,
        }
