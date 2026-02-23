"""Tests for src/dashboard/components/performance_metrics.py — pure math functions."""
import pytest
import numpy as np
import pandas as pd

from src.dashboard.components.performance_metrics import (
    compute_cumulative_returns,
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe_ratio,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _series(values, start="2023-01-01", freq="D"):
    """Create a DatetimeIndex Series from a list of values."""
    idx = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx)


# ── Cumulative Returns ────────────────────────────────────────────────────────

class TestCumulativeReturns:
    def test_basic(self):
        s = _series([100, 110, 105])
        result = compute_cumulative_returns(s)
        assert result.iloc[0] == pytest.approx(100.0)
        assert result.iloc[1] == pytest.approx(110.0)
        assert result.iloc[2] == pytest.approx(105.0)

    def test_different_base(self):
        s = _series([200, 220])
        result = compute_cumulative_returns(s)
        assert result.iloc[0] == pytest.approx(100.0)
        assert result.iloc[1] == pytest.approx(110.0)

    def test_empty(self):
        s = pd.Series([], dtype=float)
        result = compute_cumulative_returns(s)
        assert result.empty


# ── CAGR ──────────────────────────────────────────────────────────────────────

class TestCAGR:
    def test_double_in_one_year(self):
        """100 → 200 over 365 days ≈ 100% CAGR."""
        s = _series([100, 200], start="2023-01-01", freq="365D")
        result = compute_cagr(s)
        assert result == pytest.approx(100.0, rel=0.02)  # ~100%

    def test_no_change(self):
        """100 → 100 over any period = 0% CAGR."""
        s = _series([100, 100], start="2023-01-01", freq="365D")
        assert compute_cagr(s) == pytest.approx(0.0)

    def test_50_pct_gain(self):
        """100 → 150 over 1 year ≈ 50% CAGR."""
        s = _series([100, 150], start="2023-01-01", freq="365D")
        result = compute_cagr(s)
        assert result == pytest.approx(50.0, rel=0.02)

    def test_fewer_than_2_points(self):
        s = _series([100])
        assert compute_cagr(s) == 0.0

    def test_empty(self):
        s = pd.Series([], dtype=float)
        assert compute_cagr(s) == 0.0

    def test_zero_start(self):
        """Start value 0 → returns 0."""
        s = _series([0, 100], start="2023-01-01", freq="365D")
        assert compute_cagr(s) == 0.0

    def test_same_day(self):
        """Same-day series → days=0 → returns 0."""
        idx = pd.DatetimeIndex(["2023-01-01", "2023-01-01"])
        s = pd.Series([100, 110], index=idx)
        assert compute_cagr(s) == 0.0


# ── Max Drawdown ──────────────────────────────────────────────────────────────

class TestMaxDrawdown:
    def test_simple_drawdown(self):
        """100 → 120 → 90 → drawdown = (90-120)/120 = -25%."""
        s = _series([100, 120, 90])
        result = compute_max_drawdown(s)
        assert result == pytest.approx(-25.0)

    def test_no_drawdown(self):
        """Monotonically increasing → 0%."""
        s = _series([100, 110, 120, 130])
        result = compute_max_drawdown(s)
        assert result == pytest.approx(0.0)

    def test_full_loss(self):
        """100 → 0 → -100%."""
        s = _series([100, 50, 0.001])
        result = compute_max_drawdown(s)
        assert result < -99.0

    def test_fewer_than_2_points(self):
        s = _series([100])
        assert compute_max_drawdown(s) == 0.0

    def test_recovery_doesnt_affect_max_dd(self):
        """100 → 80 → 120 → max DD is still -20%."""
        s = _series([100, 80, 120])
        result = compute_max_drawdown(s)
        assert result == pytest.approx(-20.0, rel=0.01)


# ── Sharpe Ratio ──────────────────────────────────────────────────────────────

class TestSharpeRatio:
    def test_fewer_than_30_points(self):
        """Returns 0 with insufficient data."""
        s = _series(list(range(100, 129)))
        assert compute_sharpe_ratio(s) == 0.0

    def test_flat_returns(self):
        """Constant series → std=0 → returns 0."""
        s = _series([100] * 50)
        assert compute_sharpe_ratio(s) == 0.0

    def test_positive_returns(self):
        """Steadily increasing → positive Sharpe."""
        np.random.seed(42)
        values = 100 + np.cumsum(np.random.normal(0.1, 0.5, 60))
        s = _series(values.tolist())
        result = compute_sharpe_ratio(s, risk_free_annual=0.04)
        assert result > 0  # positive excess returns with low vol

    def test_negative_returns(self):
        """Steadily decreasing → negative Sharpe."""
        np.random.seed(42)
        values = 100 + np.cumsum(np.random.normal(-0.3, 0.5, 60))
        s = _series(values.tolist())
        result = compute_sharpe_ratio(s, risk_free_annual=0.04)
        assert result < 0

    def test_custom_risk_free(self):
        """Different risk-free rate changes the result."""
        np.random.seed(42)
        values = 100 + np.cumsum(np.random.normal(0.05, 0.5, 60))
        s = _series(values.tolist())
        sharpe_low_rf = compute_sharpe_ratio(s, risk_free_annual=0.01)
        sharpe_high_rf = compute_sharpe_ratio(s, risk_free_annual=0.10)
        assert sharpe_low_rf > sharpe_high_rf
