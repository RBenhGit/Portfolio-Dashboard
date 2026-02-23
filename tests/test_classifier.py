"""Tests for src/classifiers/ibi_classifier.py — 21 transaction types."""
import pytest
from src.classifiers.ibi_classifier import IBIClassifier


@pytest.fixture
def clf():
    return IBIClassifier()


def _row(tx_type, currency="₪", symbol="12345", name="Test Stock",
         quantity=10.0, execution_price_raw=17000, amount_lc=-1700,
         amount_fc=0.0, commission=5, additional_fees=0, balance=0,
         capital_gains_tax_estimate=0, row_hash="abc123", **kw):
    d = {
        "date": "2024-01-01",
        "transaction_type": tx_type,
        "currency": currency,
        "security_symbol": symbol,
        "security_name": name,
        "quantity": quantity,
        "execution_price_raw": execution_price_raw,
        "amount_local_currency": amount_lc,
        "amount_foreign_currency": amount_fc,
        "commission": commission,
        "additional_fees": additional_fees,
        "balance": balance,
        "capital_gains_tax_estimate": capital_gains_tax_estimate,
        "row_hash": row_hash,
    }
    d.update(kw)
    return d


# ── Phantom Detection ─────────────────────────────────────────────────────────

class TestPhantomDetection:
    def test_symbol_prefix_999(self, clf):
        assert clf.detect_phantom({"security_symbol": "9993983", "security_name": ""})

    def test_symbol_99028(self, clf):
        assert clf.detect_phantom({"security_symbol": "99028", "security_name": ""})

    def test_symbol_5039813(self, clf):
        assert clf.detect_phantom({"security_symbol": "5039813", "security_name": ""})

    def test_name_keyword(self, clf):
        assert clf.detect_phantom({"security_symbol": "12345", "security_name": "מס לשלם"})

    def test_non_phantom(self, clf):
        assert not clf.detect_phantom({"security_symbol": "12345", "security_name": "בנק לאומי"})


# ── Price Normalization ───────────────────────────────────────────────────────

class TestPriceNormalization:
    def test_nis_agorot_to_shekel(self, clf):
        """TASE NIS prices in agorot → ÷100."""
        assert clf.normalize_price(17000, "₪") == pytest.approx(170.0)

    def test_usd_no_change(self, clf):
        """USD prices unchanged."""
        assert clf.normalize_price(150.5, "$") == pytest.approx(150.5)

    def test_zero_price(self, clf):
        assert clf.normalize_price(0, "₪") == 0.0
        assert clf.normalize_price(0, "$") == 0.0


# ── NIS Buy Types ─────────────────────────────────────────────────────────────

class TestNisBuys:
    @pytest.mark.parametrize("tx_type", ["קניה שח", "קניה רצף", "קניה מעוף"])
    def test_nis_buy(self, clf, tx_type):
        result = clf.classify(_row(tx_type))
        assert result["effect"] == "buy"
        assert result["share_direction"] == "add"
        assert result["share_quantity_abs"] == 10.0
        assert result["execution_price"] == pytest.approx(170.0)  # 17000/100
        assert result["cost_basis"] == 1700.0  # abs(-1700)
        assert result["cash_flow_nis"] == -1700.0

    def test_forex_buy_99028(self, clf):
        """Symbol 99028 with קניה שח → forex_buy, phantom."""
        row = _row("קניה שח", symbol="99028", quantity=1000,
                   amount_lc=-3700, amount_fc=0)
        result = clf.classify(row)
        assert result["effect"] == "forex_buy"
        assert result["is_phantom"] is True
        assert result["cash_flow_nis"] == -3700.0
        assert result["cash_flow_usd"] == 1000.0


# ── USD Buy ───────────────────────────────────────────────────────────────────

class TestUsdBuy:
    def test_usd_buy(self, clf):
        row = _row("קניה חול מטח", currency="$", symbol="AAPL",
                   execution_price_raw=150, quantity=10, amount_fc=-1500)
        result = clf.classify(row)
        assert result["effect"] == "buy"
        assert result["share_direction"] == "add"
        assert result["share_quantity_abs"] == 10.0
        assert result["cost_basis"] == 1500.0
        assert result["cash_flow_usd"] == -1500.0


# ── Sell Types ────────────────────────────────────────────────────────────────

class TestSells:
    @pytest.mark.parametrize("tx_type", ["מכירה שח", "מכירה רצף", "מכירה מעוף"])
    def test_nis_sell(self, clf, tx_type):
        row = _row(tx_type, quantity=10, amount_lc=2000)
        result = clf.classify(row)
        assert result["effect"] == "sell"
        assert result["share_direction"] == "remove"
        assert result["share_quantity_abs"] == 10.0
        assert result["cash_flow_nis"] == 2000.0

    def test_usd_sell(self, clf):
        row = _row("מכירה חול מטח", currency="$", symbol="AAPL",
                   quantity=5, amount_fc=750)
        result = clf.classify(row)
        assert result["effect"] == "sell"
        assert result["share_direction"] == "remove"
        assert result["cash_flow_usd"] == 750.0


# ── Deposit / Withdrawal ─────────────────────────────────────────────────────

class TestDepositWithdrawal:
    def test_deposit(self, clf):
        row = _row("הפקדה", quantity=50)
        result = clf.classify(row)
        assert result["effect"] == "deposit"
        assert result["share_direction"] == "add"
        assert result["share_quantity_abs"] == 50.0

    def test_withdrawal(self, clf):
        row = _row("משיכה", quantity=20)
        result = clf.classify(row)
        assert result["effect"] == "withdrawal"
        assert result["share_direction"] == "remove"
        assert result["share_quantity_abs"] == 20.0


# ── Option Expiry ─────────────────────────────────────────────────────────────

class TestOptionExpiry:
    def test_expiry_credit(self, clf):
        row = _row("הפקדה פקיעה", quantity=100, symbol="80001234")
        result = clf.classify(row)
        assert result["effect"] == "option_expiry"
        assert result["share_direction"] == "add"

    def test_expiry_debit(self, clf):
        row = _row("משיכה פקיעה", quantity=100, symbol="80001234")
        result = clf.classify(row)
        assert result["effect"] == "option_expiry"
        assert result["share_direction"] == "remove"


# ── Stock Split / Bonus ───────────────────────────────────────────────────────

class TestStockSplitBonus:
    def test_hatava_zero_price_is_split(self, clf):
        """הטבה with execution_price_raw=0 → stock_split."""
        row = _row("הטבה", execution_price_raw=0, quantity=100)
        result = clf.classify(row)
        assert result["effect"] == "stock_split"
        assert result["share_direction"] == "add"
        assert result["share_quantity_abs"] == 100.0

    def test_hatava_positive_price_is_bonus(self, clf):
        """הטבה with execution_price_raw>0 → bonus_or_split."""
        row = _row("הטבה", execution_price_raw=5000, quantity=10)
        result = clf.classify(row)
        assert result["effect"] == "bonus_or_split"
        assert result["cost_basis"] == 0.0


# ── Dividends ─────────────────────────────────────────────────────────────────

class TestDividends:
    def test_nis_dividend(self, clf):
        row = _row("דיבדנד", amount_lc=500, quantity=0)
        result = clf.classify(row)
        assert result["effect"] == "dividend"
        assert result["cash_flow_nis"] == 500.0

    def test_usd_dividend(self, clf):
        row = _row("הפקדה דיבידנד מטח", currency="$", symbol="99028",
                   amount_fc=200, quantity=0)
        result = clf.classify(row)
        assert result["effect"] == "dividend"
        assert result["cash_flow_usd"] == 200.0
        assert result["is_phantom"] is True


# ── Interest / Tax / Fee / Transfer ──────────────────────────────────────────

class TestOtherTypes:
    def test_interest(self, clf):
        row = _row("ריבית מזומן בשח", amount_lc=100, quantity=0)
        result = clf.classify(row)
        assert result["effect"] == "interest"
        assert result["cash_flow_nis"] == 100.0

    def test_interest_tax_phantom(self, clf):
        row = _row("משיכת ריבית מטח", currency="$", amount_fc=-50, quantity=0)
        result = clf.classify(row)
        assert result["effect"] == "interest_tax"
        assert result["is_phantom"] is True
        assert result["cash_flow_usd"] == -50.0

    @pytest.mark.parametrize("tx_type", ["משיכת מס חול מטח", "משיכת מס מטח"])
    def test_foreign_tax(self, clf, tx_type):
        row = _row(tx_type, currency="$", amount_fc=-30, quantity=0)
        result = clf.classify(row)
        assert result["effect"] == "tax"
        assert result["is_phantom"] is True

    def test_transfer(self, clf):
        row = _row("העברה מזומן בשח", amount_lc=10000, quantity=0)
        result = clf.classify(row)
        assert result["effect"] == "transfer"
        assert result["cash_flow_nis"] == 10000.0

    def test_fee(self, clf):
        row = _row("דמי טפול מזומן בשח", amount_lc=-25, quantity=0)
        result = clf.classify(row)
        assert result["effect"] == "fee"
        assert result["cash_flow_nis"] == -25.0


# ── Market Detection ─────────────────────────────────────────────────────────

class TestMarketDetection:
    def test_nis_tase(self, clf):
        row = _row("קניה שח", currency="₪", symbol="445015")
        result = clf.classify(row)
        assert result["market"] == "TASE"

    def test_usd_us(self, clf):
        row = _row("קניה חול מטח", currency="$", symbol="AAPL",
                   execution_price_raw=150, amount_fc=-1500)
        result = clf.classify(row)
        assert result["market"] == "US"


# ── Output Fields ─────────────────────────────────────────────────────────────

class TestOutputFields:
    def test_all_required_fields_present(self, clf):
        result = clf.classify(_row("קניה שח"))
        expected_keys = {
            "date", "transaction_type", "effect", "is_phantom",
            "security_name", "security_symbol", "market", "currency",
            "quantity", "execution_price_raw", "execution_price",
            "commission", "additional_fees",
            "amount_foreign_currency", "amount_local_currency",
            "balance", "capital_gains_tax_estimate", "row_hash",
            "share_direction", "share_quantity_abs", "cost_basis",
            "cash_flow_nis", "cash_flow_usd", "fx_rate_on_date", "cost_basis_nis",
        }
        assert expected_keys.issubset(result.keys())
