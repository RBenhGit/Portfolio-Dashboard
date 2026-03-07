"""Market detection and TASE symbol handling.

TASE stocks on IBI use numeric IDs (e.g. 445015 for Matrix IT).
Twelvedata and yfinance use alphabetic tickers (MTRX, MTRX.TA).
This module resolves IBI IDs → API-compatible ticker symbols.
"""
import logging
import re
from typing import Optional

import requests

from src.config import TWELVEDATA_API_KEY

logger = logging.getLogger(__name__)

_US_TICKER_RE   = re.compile(r'^[A-Z]{1,6}$')
_TASE_NUM_RE    = re.compile(r'^\d{5,8}$')
_OPTION_RE      = re.compile(r'^[89]\d{7}$')
_OPTION_NAME_RE = re.compile(r'^ת[A-Z]\d+M\d+-\d+$')  # e.g. תP001440M212-35

# Known IBI numeric ID → Twelvedata ticker (static fallback)
_KNOWN_TASE_MAP: dict[str, dict] = {
    "288019":  {"td": "SCOP",     "yf": "SCOP.TA",     "name": "Scope Metals Group"},
    "445015":  {"td": "MTRX",     "yf": "MTRX.TA",     "name": "Matrix IT"},
    "507012":  {"td": "CMDR",     "yf": "CMDR.TA",     "name": "Computer Direct"},
    "695437":  {"td": "MZTF",     "yf": "MZTF.TA",     "name": "Mizrahi Tefahot Bank"},
    "1176593": {"td": "NXSN",     "yf": "NXSN.TA",     "name": "Next Vision Stabilized Systems"},
    "315010":  {"td": "FBRT",     "yf": "FBRT.TA",     "name": "FMS Enterprises Migun"},
    "1083955": {"td": "QLTU",     "yf": "QLTU.TA",     "name": "QualiTau"},
    "1080456": {"td": "RIMO",     "yf": "RIMO.TA",     "name": "Rimoni Industries"},
    "1080753": {"td": "ILX",      "yf": "ILX.TA",      "name": "Ilex Medical"},
    "1131523": {"td": "BOTI",     "yf": "BOTI.TA",     "name": "Bonei Hatichon"},
    "1141464": {"td": "MRIN",     "yf": "MRIN.TA",     "name": "Y.D. More Investments"},
    "1143718": {"td": "TCH.F139", "yf": "TCH-F139.TA", "name": "Tachlit TA-125 ETF"},
}

# Runtime cache (populated from DB + API lookups)
_resolved_cache: dict[str, dict] = {}


def detect_market(security_symbol: str, currency: str) -> str:
    """Determine TASE vs US market for a security."""
    sym = str(security_symbol or "").strip()
    cur = str(currency or "").strip()
    # Numeric IDs (5-8 digits) are always TASE instruments,
    # even if denominated in $ (e.g. dollar-linked bonds/ETFs)
    if _TASE_NUM_RE.match(sym):
        return "TASE"
    if cur == "$":
        return "US"
    if cur == "₪" and _US_TICKER_RE.match(sym):
        return "US"   # dual-listed ETF/ADR
    return "TASE"


def is_option(security_symbol: str, security_name: Optional[str] = None) -> bool:
    """Return True if this is an option/warrant — skip pricing."""
    sym  = str(security_symbol or "").strip()
    name = str(security_name or "").strip()
    return bool(_OPTION_RE.match(sym) or _OPTION_NAME_RE.match(name))


def resolve_tase_symbol(ibi_id: str, security_name: Optional[str] = None) -> dict | None:
    """Resolve an IBI numeric ID to Twelvedata/yfinance ticker symbols.

    Returns {"td": "MTRX", "yf": "MTRX.TA", "name": "Matrix IT"} or None.
    Checks: runtime cache → DB cache → static map → Twelvedata search API.
    """
    ibi_id = str(ibi_id).strip()

    # 1. Runtime cache
    if ibi_id in _resolved_cache:
        return _resolved_cache[ibi_id]

    # 2. DB cache
    from src.database import repository
    db_row = repository.get_tase_symbol(ibi_id)
    if db_row and db_row.get("td_symbol"):
        result = {"td": db_row["td_symbol"], "yf": db_row["yf_symbol"], "name": db_row["name"]}
        _resolved_cache[ibi_id] = result
        return result

    # 3. Static known map
    if ibi_id in _KNOWN_TASE_MAP:
        result = _KNOWN_TASE_MAP[ibi_id]
        _resolved_cache[ibi_id] = result
        repository.upsert_tase_symbol(ibi_id, result["td"], result["yf"], result["name"])
        logger.info("TASE symbol %s resolved from static map → %s", ibi_id, result["td"])
        return result

    # 4. Twelvedata symbol_search API (by security name)
    if security_name and TWELVEDATA_API_KEY:
        td_ticker = _search_twelvedata(security_name)
        if td_ticker:
            result = {"td": td_ticker, "yf": f"{td_ticker}.TA", "name": security_name}
            _resolved_cache[ibi_id] = result
            repository.upsert_tase_symbol(ibi_id, result["td"], result["yf"], result["name"])
            logger.info("TASE symbol %s resolved via API search → %s", ibi_id, td_ticker)
            return result

    logger.warning("Could not resolve TASE symbol for IBI ID %s (name=%s)", ibi_id, security_name)
    return None


# IBI abbreviated Hebrew prefixes → full names for better search results
_HEBREW_ABBREVS = {
    "תכ.":  "תכלית ",
    "קסם.": "קסם ",
    "הראל.": "הראל ",
    "מגדל.": "מגדל ",
    "אנלי.": "אנליסט ",
    "מיט.":  "מיטב ",
    "פסג.":  "פסגות ",
    "אלט.":  "אלטשולר ",
}


def _clean_hebrew_name(name: str) -> str:
    """Expand IBI abbreviated Hebrew names for better API search.

    E.g. 'תכ.תלבונדשקלי' → 'תכלית תל-בונד שקלי'
    """
    cleaned = name.strip()
    for abbrev, full in _HEBREW_ABBREVS.items():
        if cleaned.startswith(abbrev):
            cleaned = full + cleaned[len(abbrev):]
            break
    # Insert spaces before capitals and between Hebrew word boundaries
    # (IBI often concatenates words: 'תלבונדשקלי' → keep as is, API may match)
    return cleaned


def _search_twelvedata(name: str) -> str | None:
    """Search Twelvedata for a TASE stock by name. Returns ticker or None.

    Tries the original name first, then a cleaned-up version.
    """
    candidates = [name]
    cleaned = _clean_hebrew_name(name)
    if cleaned != name:
        candidates.append(cleaned)

    for query in candidates:
        try:
            resp = requests.get(
                "https://api.twelvedata.com/symbol_search",
                params={"symbol": query, "exchange": "TASE", "apikey": TWELVEDATA_API_KEY},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            for item in data:
                if item.get("exchange") == "TASE":
                    return item["symbol"]
        except Exception as exc:
            logger.warning("Twelvedata symbol search failed for '%s': %s", query, exc)
    return None


def tase_yfinance_symbol(tase_id: str, security_name: Optional[str] = None) -> str:
    """Resolve IBI ID to yfinance symbol, or fallback to ID.TA."""
    resolved = resolve_tase_symbol(tase_id, security_name)
    if resolved:
        return resolved["yf"]
    return f"{tase_id}.TA"


def twelvedata_params(security_symbol: str, market: str,
                      security_name: Optional[str] = None) -> dict:
    """Build Twelvedata /price query params for a symbol."""
    if market == "TASE":
        resolved = resolve_tase_symbol(security_symbol, security_name)
        td_sym = resolved["td"] if resolved else security_symbol
        return {"symbol": td_sym, "exchange": "TASE"}
    return {"symbol": security_symbol}
