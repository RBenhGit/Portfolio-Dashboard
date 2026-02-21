"""USD/ILS historical and current exchange rate fetcher.

Primary: Twelvedata  |  Fallback: yfinance
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)
_TD_BASE = "https://api.twelvedata.com"


def _api_key() -> str:
    from src.config import TWELVEDATA_API_KEY
    return TWELVEDATA_API_KEY


def fetch_historical_fx(missing_dates: list[str]) -> dict[str, float]:
    """Fetch USD/ILS for a list of YYYY-MM-DD dates.

    Returns {date_str: rate}.  Uses Twelvedata bulk, yfinance for gaps.
    """
    if not missing_dates:
        return {}

    rates: dict[str, float] = {}
    remaining = set(missing_dates)

    try:
        rates.update(_td_timeseries(remaining))
        remaining -= set(rates)
    except Exception as exc:
        logger.warning("Twelvedata FX time_series failed: %s", exc)

    if remaining:
        try:
            rates.update(_yf_fx(list(remaining)))
        except Exception as exc:
            logger.warning("yfinance FX fallback failed: %s", exc)

    return rates


def _td_timeseries(date_set: set[str]) -> dict[str, float]:
    key = _api_key()
    if not key:
        raise ValueError("TWELVEDATA_API_KEY not set")
    resp = requests.get(
        f"{_TD_BASE}/time_series",
        params={"symbol": "USD/ILS", "interval": "1day", "outputsize": 5000, "apikey": key},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error":
        raise ValueError(data.get("message", "Twelvedata error"))
    return {
        item["datetime"][:10]: float(item["close"])
        for item in data.get("values", [])
        if item["datetime"][:10] in date_set
    }


def _yf_fx(dates: list[str]) -> dict[str, float]:
    import yfinance as yf
    if not dates:
        return {}
    min_d = min(dates)
    max_d = max(dates)
    end_d = (datetime.strptime(max_d, "%Y-%m-%d") + timedelta(days=5)).strftime("%Y-%m-%d")
    hist = yf.Ticker("USDILS=X").history(start=min_d, end=end_d, interval="1d")
    if hist.empty:
        return {}
    hist.index = hist.index.strftime("%Y-%m-%d")
    date_set = set(dates)
    rates: dict[str, float] = {}
    for d in date_set:
        if d in hist.index:
            rates[d] = float(hist.loc[d, "Close"])
        else:
            prior = [x for x in hist.index if x <= d]
            if prior:
                rates[d] = float(hist.loc[max(prior), "Close"])
    return rates


def get_current_fx_rate() -> Optional[float]:
    """Return the live USD/ILS rate for display."""
    try:
        return _td_current()
    except Exception:
        pass
    try:
        return _yf_current()
    except Exception:
        return None


def _td_current() -> float:
    key = _api_key()
    if not key:
        raise ValueError("No API key")
    resp = requests.get(
        f"{_TD_BASE}/exchange_rate",
        params={"symbol": "USD/ILS", "apikey": key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error":
        raise ValueError(data.get("message"))
    return float(data["rate"])


def _yf_current() -> float:
    import yfinance as yf
    hist = yf.Ticker("USDILS=X").history(period="2d", interval="1d")
    if hist.empty:
        raise ValueError("yfinance empty")
    return float(hist["Close"].iloc[-1])
