"""Historical closing price fetcher — Twelvedata primary, yfinance fallback.

Fetches the end-of-day closing price for a given date (not live prices).

TASE agorot convention:
  TASE prices MAY come back in agorot from APIs.
  We auto-detect on first fetch and store only shekel values.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

import re

from src.config import TWELVEDATA_API_KEY, YFINANCE_ENABLED
from src.database import repository
from src.market.symbol_mapper import (
    is_option, resolve_tase_symbol, resolve_us_numeric_ticker,
    tase_yfinance_symbol, twelvedata_params,
)

_TASE_NUM_RE = re.compile(r'^\d{5,8}$')

logger = logging.getLogger(__name__)
_TD_BASE = "https://api.twelvedata.com"
_last_source = "unknown"


def get_price(security_symbol: str, market: str,
              security_name: Optional[str] = None,
              price_date: str = "") -> Optional[float]:
    """Return closing price on *price_date* in shekels (TASE) or dollars (US)."""
    if is_option(security_symbol, security_name):
        return None

    cached = repository.get_cached_price(security_symbol, market, price_date)
    if cached is not None:
        return cached

    price = _fetch_historical(security_symbol, market, security_name, price_date)
    if price is not None:
        currency = "₪" if market == "TASE" else "$"
        repository.upsert_price(security_symbol, market, price, currency,
                                _last_source, price_date)
    return price


def _fetch_historical(symbol: str, market: str,
                      security_name: Optional[str] = None,
                      price_date: str = "") -> Optional[float]:
    """Fetch the closing price for *symbol* on *price_date*."""
    global _last_source

    # For US stocks stored with a numeric IBI ID, resolve to the real ticker first
    if market == "US" and _TASE_NUM_RE.match(symbol):
        real_ticker = resolve_us_numeric_ticker(symbol)
        if real_ticker:
            symbol = real_ticker
        else:
            logger.warning(
                "Skipping price fetch: unknown US numeric IBI ID %s (%s) on %s",
                symbol, security_name or "unknown", price_date,
            )
            return None

    # For TASE numeric IDs, resolve first — skip all API calls if unresolvable
    if market == "TASE" and _TASE_NUM_RE.match(symbol):
        resolved = resolve_tase_symbol(symbol, security_name)
        if not resolved:
            logger.warning(
                "Skipping price fetch for unresolvable TASE ID %s (%s) on %s",
                symbol, security_name or "unknown", price_date,
            )
            return None

    if TWELVEDATA_API_KEY:
        try:
            p = _fetch_td_historical(symbol, market, security_name, price_date)
            if p is not None:
                _last_source = "twelvedata"
                return p
        except Exception as exc:
            logger.warning("Twelvedata historical price failed for %s on %s: %s",
                           symbol, price_date, exc)

    if YFINANCE_ENABLED:
        try:
            p = _fetch_yf_historical(symbol, market, security_name, price_date)
            if p is not None:
                _last_source = "yfinance"
                return p
        except Exception as exc:
            logger.warning("yfinance historical price failed for %s on %s: %s",
                           symbol, price_date, exc)

    logger.error("All price sources failed for %s (market=%s, date=%s)",
                 symbol, market, price_date)
    return None


def _fetch_td_historical(symbol: str, market: str,
                         security_name: Optional[str] = None,
                         price_date: str = "") -> Optional[float]:
    """Fetch closing price from Twelvedata /time_series for a single date."""
    params = twelvedata_params(symbol, market, security_name)
    params.update({
        "apikey": TWELVEDATA_API_KEY,
        "interval": "1day",
        "start_date": price_date,
        "end_date": price_date,
        "outputsize": 5,
    })
    resp = requests.get(f"{_TD_BASE}/time_series", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") == "error":
        logger.warning("Twelvedata time_series error for %s: %s",
                       symbol, data.get("message", data))
        return None

    values = data.get("values", [])
    if not values:
        logger.warning("Twelvedata returned no values for %s on %s", symbol, price_date)
        return None

    # Use the closest date <= price_date
    for item in values:
        item_date = item["datetime"][:10]
        if item_date <= price_date:
            price = float(item["close"])
            logger.info("Twelvedata historical price for %s on %s: %.4f",
                        params.get("symbol"), item_date, price)
            return _normalize_tase(price, market, "twelvedata")

    return None


def _fetch_yf_historical(symbol: str, market: str,
                         security_name: Optional[str] = None,
                         price_date: str = "") -> Optional[float]:
    """Fetch closing price from yfinance for a specific date."""
    import yfinance as yf

    yf_sym = tase_yfinance_symbol(symbol, security_name) if market == "TASE" else symbol
    logger.info("yfinance fetching historical %s for %s (original=%s)",
                yf_sym, price_date, symbol)

    start = price_date
    end_dt = datetime.strptime(price_date, "%Y-%m-%d") + timedelta(days=5)
    end = end_dt.strftime("%Y-%m-%d")

    ticker = yf.Ticker(yf_sym)
    hist = ticker.history(start=start, end=end)

    if hist.empty:
        logger.warning("yfinance returned no history for %s around %s", yf_sym, price_date)
        return None

    hist.index = hist.index.strftime("%Y-%m-%d")

    # Try exact date first, then closest prior date
    if price_date in hist.index:
        price = float(hist.loc[price_date, "Close"])
    else:
        prior = [d for d in hist.index if d <= price_date]
        if prior:
            price = float(hist.loc[max(prior), "Close"])
        else:
            price = float(hist["Close"].iloc[0])

    return _normalize_tase(price, market, "yfinance")


def _normalize_tase(price: float, market: str, source: str) -> float:
    """Convert TASE price to shekels if the source returns agorot (ILA).

    yfinance always returns TASE prices in ILA (agorot) — divide by 100.
    Twelvedata: per-price heuristic (no global state).
    """
    if market != "TASE":
        return price

    if source == "yfinance":
        # yfinance .TA always reports currency=ILA (agorot)
        return price / 100.0

    # Twelvedata or unknown source: per-price heuristic.
    # No TASE stock trades above ₪10,000; prices above that are agorot.
    if price > 10_000:
        logger.info(
            "TASE price=%.2f > 10000 → likely agorot (%s), dividing by 100",
            price, source,
        )
        return price / 100.0
    return price


def fetch_prices_for_positions(positions: dict,
                               price_date: str = "") -> dict[str, Optional[float]]:
    """Fetch historical closing prices for all open positions."""
    return {sym: get_price(sym, pos.market, pos.security_name, price_date)
            for sym, pos in positions.items()}


def check_twelvedata_status() -> bool:
    """Return True if Twelvedata API key is valid and reachable."""
    if not TWELVEDATA_API_KEY:
        return False
    try:
        resp = requests.get(
            f"{_TD_BASE}/api_usage",
            params={"apikey": TWELVEDATA_API_KEY},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False
