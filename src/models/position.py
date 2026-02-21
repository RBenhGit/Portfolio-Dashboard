"""Position dataclass — tracks a single holding during portfolio build."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Position:
    security_symbol: str
    security_name: Optional[str]
    market: str        # 'TASE' | 'US'
    currency: str      # '₪' | '$'

    quantity: float = 0.0
    total_invested: float = 0.0       # native currency (sum of cost_basis)
    total_invested_nis: float = 0.0   # cost basis in ₪ via historical FX

    # Set by price_fetcher after build
    market_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None

    @property
    def average_cost(self) -> float:
        return self.total_invested / self.quantity if self.quantity > 0 else 0.0

    def to_snapshot_dict(self) -> dict:
        return {
            "security_symbol": self.security_symbol,
            "security_name": self.security_name,
            "market": self.market,
            "currency": self.currency,
            "quantity": self.quantity,
            "average_cost": self.average_cost,
            "total_invested": self.total_invested,
            "total_invested_nis": self.total_invested_nis,
            "market_price": self.market_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
        }
