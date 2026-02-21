"""Abstract base classifier — broker-agnostic interface."""
from abc import ABC, abstractmethod


class BaseClassifier(ABC):
    """Abstract base for all broker transaction classifiers."""

    @abstractmethod
    def classify(self, row: dict) -> dict:
        """Classify a raw transaction row.

        Returns a dict with all Transaction fields including:
        effect, share_direction, share_quantity_abs, execution_price,
        cost_basis, cash_flow_nis, cash_flow_usd, is_phantom, market.
        """

    @abstractmethod
    def detect_phantom(self, row: dict) -> bool:
        """Return True if this row is a phantom/internal IBI account entry."""

    def normalize_price(self, raw_price: float, currency: str) -> float:
        """Convert raw execution price to display units.

        TASE (₪): IBI stores in agorot → divide by 100.
        US ($): already in dollars → no change.
        """
        if currency and currency.strip() == "₪":
            return (raw_price / 100.0) if raw_price else 0.0
        return raw_price or 0.0
