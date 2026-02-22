"""Fetch benchmark index data (S&P 500, TA-125) via yfinance with SQLite caching."""
import logging
from datetime import datetime, timedelta

from src.database import repository

logger = logging.getLogger(__name__)

BENCHMARKS = {
    "S&P 500": "^GSPC",
    "TA-125": "^TA125.TA",
}


def fetch_benchmark(name: str, start_date: str, end_date: str) -> dict[str, float]:
    """Fetch daily closes for a benchmark index.

    Args:
        name: key from BENCHMARKS (e.g. "S&P 500")
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD

    Returns:
        {date_str: close_price} filtered to the requested range.
    """
    yf_symbol = BENCHMARKS[name]

    # Check cache
    cached = repository.get_benchmark_prices(yf_symbol)
    cached_min, cached_max = repository.get_benchmark_date_range(yf_symbol)

    need_fetch = True
    if cached_min and cached_max and cached_min <= start_date and cached_max >= end_date:
        need_fetch = False

    if need_fetch:
        try:
            new_prices = _fetch_from_yfinance(yf_symbol, start_date, end_date,
                                              cached_min, cached_max)
            if new_prices:
                repository.upsert_benchmark_prices(yf_symbol, new_prices)
                cached.update(new_prices)
        except Exception as exc:
            logger.warning("Failed to fetch benchmark %s (%s): %s", name, yf_symbol, exc)

    # Filter to requested range
    return {d: p for d, p in cached.items() if start_date <= d <= end_date}


def _fetch_from_yfinance(yf_symbol: str, start_date: str, end_date: str,
                         cached_min: str | None, cached_max: str | None) -> dict[str, float]:
    """Fetch only the missing date ranges from yfinance."""
    import yfinance as yf

    ranges_to_fetch = []

    if cached_min is None:
        # No cache at all — fetch full range
        ranges_to_fetch.append((start_date, end_date))
    else:
        # Fetch before cached range
        if start_date < cached_min:
            ranges_to_fetch.append((start_date, cached_min))
        # Fetch after cached range
        if end_date > cached_max:
            ranges_to_fetch.append((cached_max, end_date))

    all_prices: dict[str, float] = {}
    for fetch_start, fetch_end in ranges_to_fetch:
        # yfinance end is exclusive, add a day
        end_dt = datetime.strptime(fetch_end, "%Y-%m-%d") + timedelta(days=1)
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(start=fetch_start, end=end_dt.strftime("%Y-%m-%d"))

        if hist.empty:
            logger.warning("yfinance returned no data for %s (%s to %s)",
                           yf_symbol, fetch_start, fetch_end)
            continue

        for idx, row in hist.iterrows():
            date_str = idx.strftime("%Y-%m-%d")
            all_prices[date_str] = float(row["Close"])

    return all_prices
