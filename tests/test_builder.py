"""Tests for src/portfolio/builder.py — portfolio building algorithm."""
import pytest
from unittest.mock import patch, MagicMock

from src.models.position import Position


# ---------------------------------------------------------------------------
# Helpers: create mock transaction dicts matching builder's expected format
# ---------------------------------------------------------------------------

def _tx(date="2024-01-01", effect="buy", direction="add", qty=10.0,
        exec_price=100.0, cost_basis=1000.0, cost_basis_nis=1000.0,
        symbol="12345", name="Test Stock", currency="₪", market="TASE",
        balance=None, cash_flow_usd=0.0, is_phantom=False,
        transaction_type="קניה שח", **kw):
    d = {
        "date": date,
        "effect": effect,
        "share_direction": direction,
        "share_quantity_abs": qty,
        "execution_price": exec_price,
        "cost_basis": cost_basis,
        "cost_basis_nis": cost_basis_nis,
        "security_symbol": symbol,
        "security_name": name,
        "currency": currency,
        "market": market,
        "balance": balance,
        "cash_flow_usd": cash_flow_usd,
        "is_phantom": is_phantom,
        "transaction_type": transaction_type,
    }
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# Tests for the build logic (we test the inner loop, not the full build()
# which depends on the database). We mock repository calls.
# ---------------------------------------------------------------------------

class TestBuildBasicFlows:
    """Test buy/sell/split/deposit flows via the full build() function."""

    @patch("src.portfolio.builder.repository")
    def test_single_nis_buy(self, mock_repo):
        """A single NIS buy creates one position."""
        mock_repo.get_all_transactions.return_value = [
            MagicMock(**{"__getitem__": lambda s, k: _tx()[k],
                         "keys": lambda s: _tx().keys()})
        ]
        # Simpler: just use dict rows
        mock_repo.get_all_transactions.return_value = [_tx()]
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None
        mock_repo.insert_realized_trade.return_value = None

        from src.portfolio.builder import build
        result = build()

        assert "12345" in result["positions_nis"]
        pos = result["positions_nis"]["12345"]
        assert pos.quantity == 10.0
        assert pos.total_invested == 1000.0

    @patch("src.portfolio.builder.repository")
    def test_buy_then_sell(self, mock_repo):
        """Buy 10 then sell 5 → 5 remaining, realized trade recorded."""
        txns = [
            _tx(date="2024-01-01", effect="buy", direction="add",
                qty=10, exec_price=100, cost_basis=1000, cost_basis_nis=1000),
            _tx(date="2024-01-02", effect="sell", direction="remove",
                qty=5, exec_price=120, cost_basis=0, cost_basis_nis=0),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None
        mock_repo.insert_realized_trade.return_value = None

        from src.portfolio.builder import build
        result = build()

        assert "12345" in result["positions_nis"]
        pos = result["positions_nis"]["12345"]
        assert pos.quantity == 5.0
        # Realized trade should have been recorded
        mock_repo.insert_realized_trade.assert_called_once()
        trade = mock_repo.insert_realized_trade.call_args[0][0]
        assert trade["quantity_sold"] == 5.0
        assert trade["sale_price"] == 120.0
        assert trade["avg_cost"] == 100.0
        assert trade["realized_pnl"] == pytest.approx(100.0)  # 5*(120-100)

    @patch("src.portfolio.builder.repository")
    def test_sell_closes_position(self, mock_repo):
        """Selling all shares removes the position."""
        txns = [
            _tx(date="2024-01-01", effect="buy", direction="add",
                qty=10, exec_price=100, cost_basis=1000, cost_basis_nis=1000),
            _tx(date="2024-01-02", effect="sell", direction="remove",
                qty=10, exec_price=120, cost_basis=0, cost_basis_nis=0),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None
        mock_repo.insert_realized_trade.return_value = None

        from src.portfolio.builder import build
        result = build()

        assert "12345" not in result["positions_nis"]


class TestStockSplit:
    """Test the stock split ratio calculation."""

    @patch("src.portfolio.builder.repository")
    def test_split_doubles_shares(self, mock_repo):
        """2:1 split: 100 shares + 100 bonus = 200 shares, cost unchanged."""
        txns = [
            _tx(date="2024-01-01", effect="buy", direction="add",
                qty=100, exec_price=170, cost_basis=17000, cost_basis_nis=17000),
            _tx(date="2024-01-02", effect="stock_split", direction="add",
                qty=100, exec_price=0, cost_basis=0, cost_basis_nis=0),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None

        from src.portfolio.builder import build
        result = build()

        pos = result["positions_nis"]["12345"]
        assert pos.quantity == pytest.approx(200.0)
        assert pos.total_invested == pytest.approx(17000.0)  # unchanged
        assert pos.average_cost == pytest.approx(85.0)  # 17000/200

    @patch("src.portfolio.builder.repository")
    def test_split_ratio_calculation(self, mock_repo):
        """Verify ratio = (current + added) / current."""
        txns = [
            _tx(date="2024-01-01", effect="buy", direction="add",
                qty=50, exec_price=200, cost_basis=10000, cost_basis_nis=10000),
            _tx(date="2024-01-02", effect="stock_split", direction="add",
                qty=150, exec_price=0, cost_basis=0, cost_basis_nis=0),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None

        from src.portfolio.builder import build
        result = build()

        pos = result["positions_nis"]["12345"]
        # ratio = (50+150)/50 = 4.0 → quantity = 50*4 = 200
        assert pos.quantity == pytest.approx(200.0)
        assert pos.total_invested == pytest.approx(10000.0)
        assert pos.average_cost == pytest.approx(50.0)  # 10000/200


class TestOrphanOptionExpiry:
    """Test that orphan option expiry credits are skipped."""

    @patch("src.portfolio.builder.repository")
    def test_orphan_expiry_skipped(self, mock_repo):
        """Option expiry add with no prior short → skipped, no position."""
        txns = [
            _tx(date="2024-01-01", effect="option_expiry", direction="add",
                qty=100, exec_price=0, cost_basis=0, cost_basis_nis=0,
                symbol="80001234", name="אופציה כלשהי",
                transaction_type="הפקדה פקיעה"),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None

        from src.portfolio.builder import build
        result = build()

        # The option should NOT appear in stock positions
        assert "80001234" not in result["positions_nis"]
        # It may appear in options_nis with qty=0 (builder keeps all options
        # for UI toggle), but crucially quantity should be 0 — the expiry
        # credit was skipped, so no shares were actually added
        if "80001234" in result["options_nis"]:
            assert result["options_nis"]["80001234"].quantity == pytest.approx(0.0)


class TestUsdPositions:
    """Test USD position handling."""

    @patch("src.portfolio.builder.repository")
    def test_usd_buy(self, mock_repo):
        """USD buy goes into positions_usd."""
        txns = [
            _tx(date="2024-01-01", effect="buy", direction="add",
                qty=10, exec_price=150, cost_basis=1500, cost_basis_nis=5550,
                symbol="AAPL", name="Apple Inc", currency="$", market="US"),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None

        from src.portfolio.builder import build
        result = build()

        assert "AAPL" in result["positions_usd"]
        assert "AAPL" not in result["positions_nis"]
        pos = result["positions_usd"]["AAPL"]
        assert pos.quantity == 10.0
        assert pos.currency == "$"


class TestCashHandling:
    """Test NIS and USD cash flow tracking."""

    @patch("src.portfolio.builder.repository")
    def test_nis_balance_from_ibi(self, mock_repo):
        """NIS cash uses IBI's running balance column."""
        txns = [
            _tx(date="2024-01-01", balance=50000.0),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None

        from src.portfolio.builder import build
        result = build()

        assert result["nis_cash"] == 50000.0

    @patch("src.portfolio.builder.repository")
    def test_usd_cash_accumulates(self, mock_repo):
        """USD cash accumulates from cash_flow_usd."""
        txns = [
            _tx(date="2024-01-01", effect="dividend", direction="none",
                qty=0, is_phantom=True, cash_flow_usd=100.0,
                share_direction="none", share_quantity_abs=0),
            _tx(date="2024-01-02", effect="dividend", direction="none",
                qty=0, is_phantom=True, cash_flow_usd=50.0,
                share_direction="none", share_quantity_abs=0),
        ]
        mock_repo.get_all_transactions.return_value = txns
        mock_repo.get_fx_rate.return_value = 3.7
        mock_repo.clear_daily_portfolio_state.return_value = None
        mock_repo.clear_realized_trades.return_value = None
        mock_repo.upsert_daily_state.return_value = None

        from src.portfolio.builder import build
        result = build()

        assert result["usd_cash"] == pytest.approx(150.0)


class TestEmptyBuild:
    """Test edge cases."""

    @patch("src.portfolio.builder.repository")
    def test_no_transactions(self, mock_repo):
        """Empty DB returns empty summary."""
        mock_repo.get_all_transactions.return_value = []

        from src.portfolio.builder import build
        result = build()

        assert result["positions_nis"] == {}
        assert result["positions_usd"] == {}
        assert result["nis_cash"] == 0.0
        assert result["usd_cash"] == 0.0
