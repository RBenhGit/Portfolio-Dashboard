"""Transaction dataclass — one classified row from IBI Excel."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Transaction:
    date: str                        # YYYY-MM-DD
    transaction_type: str            # Hebrew (סוג פעולה)
    effect: str                      # buy | sell | deposit | withdrawal | dividend |
                                     # interest | tax | fee | transfer | forex_buy |
                                     # option_expiry | bonus_or_split | stock_split | none
    is_phantom: bool = False

    security_name: Optional[str] = None
    security_symbol: Optional[str] = None
    market: Optional[str] = None     # 'TASE' | 'US'
    currency: Optional[str] = None   # '₪' | '$'

    quantity: Optional[float] = None
    share_direction: str = "none"             # 'add' | 'remove' | 'none'
    share_quantity_abs: Optional[float] = None

    execution_price_raw: Optional[float] = None   # raw (agorot for TASE NIS)
    execution_price: Optional[float] = None        # normalized (÷100 for TASE)

    commission: Optional[float] = None
    additional_fees: Optional[float] = None
    amount_foreign_currency: Optional[float] = None
    amount_local_currency: Optional[float] = None
    balance: Optional[float] = None
    capital_gains_tax_estimate: Optional[float] = None

    cost_basis: Optional[float] = None       # native currency
    cash_flow_nis: float = 0.0
    cash_flow_usd: float = 0.0
    fx_rate_on_date: Optional[float] = None
    cost_basis_nis: Optional[float] = None   # cost_basis * fx_rate for USD txns

    row_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "transaction_type": self.transaction_type,
            "effect": self.effect,
            "is_phantom": int(self.is_phantom),
            "security_name": self.security_name,
            "security_symbol": self.security_symbol,
            "market": self.market,
            "currency": self.currency,
            "quantity": self.quantity,
            "share_direction": self.share_direction,
            "share_quantity_abs": self.share_quantity_abs,
            "execution_price_raw": self.execution_price_raw,
            "execution_price": self.execution_price,
            "commission": self.commission,
            "additional_fees": self.additional_fees,
            "amount_foreign_currency": self.amount_foreign_currency,
            "amount_local_currency": self.amount_local_currency,
            "balance": self.balance,
            "capital_gains_tax_estimate": self.capital_gains_tax_estimate,
            "cost_basis": self.cost_basis,
            "cash_flow_nis": self.cash_flow_nis,
            "cash_flow_usd": self.cash_flow_usd,
            "fx_rate_on_date": self.fx_rate_on_date,
            "cost_basis_nis": self.cost_basis_nis,
            "row_hash": self.row_hash,
        }
