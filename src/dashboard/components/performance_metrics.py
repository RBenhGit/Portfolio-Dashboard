"""Financial performance metrics computation."""
import numpy as np
import pandas as pd


def compute_cumulative_returns(series: pd.Series) -> pd.Series:
    """Normalize a price series to base 100."""
    if series.empty:
        return series
    return (series / series.iloc[0]) * 100


def compute_cagr(series: pd.Series) -> float:
    """Compound annual growth rate as a percentage.

    Returns 0.0 if fewer than 2 data points.
    """
    if len(series) < 2:
        return 0.0
    start_val = series.iloc[0]
    end_val = series.iloc[-1]
    if start_val <= 0:
        return 0.0
    days = (series.index[-1] - series.index[0]).days
    if days <= 0:
        return 0.0
    years = days / 365.25
    return ((end_val / start_val) ** (1 / years) - 1) * 100


def compute_max_drawdown(series: pd.Series) -> float:
    """Maximum peak-to-trough decline as a negative percentage."""
    if len(series) < 2:
        return 0.0
    cummax = series.cummax()
    drawdown = (series - cummax) / cummax
    return float(drawdown.min()) * 100


def compute_sharpe_ratio(series: pd.Series, risk_free_annual: float = 0.04) -> float:
    """Annualized Sharpe ratio using 252 trading days.

    Requires at least 30 data points. Forward-fills sparse dates before computing.
    """
    if len(series) < 30:
        return 0.0

    # Forward-fill sparse dates
    daily = series.resample("D").ffill()
    returns = daily.pct_change().dropna()

    if returns.empty or returns.std() == 0:
        return 0.0

    daily_rf = risk_free_annual / 252
    excess = returns - daily_rf
    return float(excess.mean() / excess.std() * np.sqrt(252))
