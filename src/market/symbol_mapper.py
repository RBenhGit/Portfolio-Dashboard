"""Market detection and TASE symbol handling.

TASE stocks on IBI use numeric IDs (e.g. 445015 for Matrix IT).
Twelvedata and yfinance use alphabetic tickers (MTRX, MTRX.TA).
This module resolves IBI IDs → API-compatible ticker symbols.
"""
import calendar as _calendar
import logging
import re
from datetime import date
from typing import Optional

import requests

from src.config import TWELVEDATA_API_KEY

logger = logging.getLogger(__name__)

_US_TICKER_RE   = re.compile(r'^[A-Z]{1,6}$')
_TASE_NUM_RE    = re.compile(r'^\d{5,8}$')
_OPTION_RE      = re.compile(r'^[89]\d{7}$')
_OPTION_NAME_RE = re.compile(r'^ת[A-Z]\d+M\d+-\d+$')  # e.g. תP001440M212-35
_EXPIRY_RE      = re.compile(r'M(\d)(\d{2})')           # e.g. M407 → year=4, month=07

# Known IBI numeric ID → Twelvedata ticker (static fallback, TASE stocks)
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
    "1081124": {"td": "ESLT",     "yf": "ESLT.TA",     "name": "Elbit Systems"},
    "1145184": {"td": "TCH.F34",  "yf": "TCH-F34.TA",  "name": "Tachlit Tel Bond Shekel ETF"},
    "1096106": {"td": "ATRY",     "yf": "ATRY.TA",     "name": "Atreyu Capital Markets"},
    "1184381": {"td": "MPP",      "yf": "MPP.TA",      "name": "More Provident Funds"},
}

# IBI numeric IDs that are US stocks (not TASE), keyed by IBI ID.
# IBI sometimes assigns numeric IDs to foreign stocks traded via Israeli brokers.
# These override the default "all numeric IDs → TASE" rule in detect_market.
_KNOWN_US_NUMERIC_IDS: dict[str, str] = {
    "1064054": "GOGL",     # Golden Ocean Group (NASDAQ: GOGL)
    "60217767": "SMED",    # Sharps Compliance Corp (NASDAQ: SMED)
}

# Runtime cache (populated from DB + API lookups).
# Entries are either a resolved dict or _UNRESOLVABLE to avoid repeated API calls.
_UNRESOLVABLE = object()
_resolved_cache: dict[str, object] = {}


def detect_market(security_symbol: str, currency: str) -> str:
    """Determine TASE vs US market for a security."""
    sym = str(security_symbol or "").strip()
    cur = str(currency or "").strip()
    # Some numeric IBI IDs are actually US stocks (explicit override list)
    if sym in _KNOWN_US_NUMERIC_IDS:
        return "US"
    # Numeric IDs (5-8 digits) are otherwise always TASE instruments,
    # even if denominated in $ (e.g. dollar-linked bonds/ETFs)
    if _TASE_NUM_RE.match(sym):
        return "TASE"
    if cur == "$":
        return "US"
    # ₪-denominated stocks are always TASE — dual-listed companies traded
    # in NIS on TASE are TASE positions, not US.
    return "TASE"


def resolve_us_numeric_ticker(ibi_id: str) -> str | None:
    """Return the real US ticker for a known IBI numeric ID, or None."""
    return _KNOWN_US_NUMERIC_IDS.get(str(ibi_id).strip())


def is_option(security_symbol: str, security_name: Optional[str] = None) -> bool:
    """Return True if this is an option/warrant — skip pricing."""
    sym  = str(security_symbol or "").strip()
    name = str(security_name or "").strip()
    return bool(_OPTION_RE.match(sym) or _OPTION_NAME_RE.match(name))


def parse_option_expiry(security_name: Optional[str]) -> Optional[date]:
    """Extract expiry date from a TASE option name (e.g. תP001560M407-35).

    Naming convention: M[Y][MM] where Y is the last digit of the year in the
    2020s decade (2=2022, 3=2023, 4=2024, 5=2025 …) and MM is the 2-digit
    expiry month.  Returns the last calendar day of that month, or None if the
    name does not contain a recognisable expiry token.
    """
    m = _EXPIRY_RE.search(security_name or "")
    if not m:
        return None
    try:
        year  = 2020 + int(m.group(1))
        month = int(m.group(2))
        last_day = _calendar.monthrange(year, month)[1]
        return date(year, month, last_day)
    except (ValueError, OverflowError):
        return None


def resolve_tase_symbol(ibi_id: str, security_name: Optional[str] = None) -> dict | None:
    """Resolve an IBI numeric ID to Twelvedata/yfinance ticker symbols.

    Returns {"td": "MTRX", "yf": "MTRX.TA", "name": "Matrix IT"} or None.
    Checks: runtime cache → DB cache → static map → TASE website API →
    Twelvedata search API.
    Caches failures as _UNRESOLVABLE so repeated calls skip the API search.
    """
    ibi_id = str(ibi_id).strip()

    # 1. Runtime cache (includes _UNRESOLVABLE sentinel for known failures)
    if ibi_id in _resolved_cache:
        cached = _resolved_cache[ibi_id]
        return None if cached is _UNRESOLVABLE else cached  # type: ignore[return-value]

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

    # 4. TASE public website API — authoritative security-number → symbol source
    from src.market import tase_api
    hub = tase_api.lookup_security(ibi_id)
    if hub:
        result = {"td": hub["symbol"], "yf": _yf_from_td(hub["symbol"]), "name": hub["name"]}
        _resolved_cache[ibi_id] = result
        repository.upsert_tase_symbol(ibi_id, result["td"], result["yf"], result["name"])
        logger.info("TASE symbol %s resolved via TASE API → %s", ibi_id, hub["symbol"])
        return result

    # 5. Twelvedata symbol_search API (by IBI ID, then by name)
    if TWELVEDATA_API_KEY:
        match = _search_twelvedata(ibi_id, security_name or "")
        if match:
            td_ticker, en_name = match
            result = {"td": td_ticker, "yf": _yf_from_td(td_ticker), "name": en_name}
            _resolved_cache[ibi_id] = result
            repository.upsert_tase_symbol(ibi_id, result["td"], result["yf"], result["name"])
            logger.info("TASE symbol %s resolved via API search → %s", ibi_id, td_ticker)
            return result

    # Cache the failure to avoid repeated API calls across historical dates
    _resolved_cache[ibi_id] = _UNRESOLVABLE
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


def _yf_from_td(td: str) -> str:
    """Convert Twelvedata ticker to yfinance .TA symbol (dots → dashes)."""
    return td.replace(".", "-") + ".TA"


def _search_twelvedata_once(query: str) -> tuple[str, str] | None:
    """Single Twelvedata symbol_search call. Returns (ticker, english_name) or None."""
    try:
        resp = requests.get(
            "https://api.twelvedata.com/symbol_search",
            params={"symbol": query, "exchange": "TASE", "apikey": TWELVEDATA_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            if item.get("exchange") == "TASE":
                return item["symbol"], item.get("instrument_name", query)
    except Exception as exc:
        logger.warning("Twelvedata symbol search failed for '%s': %s", query, exc)
    return None


def _search_twelvedata(ibi_id: str, name: str) -> tuple[str, str] | None:
    """Search Twelvedata for a TASE stock. Returns (ticker, english_name) or None.

    Tries numeric IBI ID first (most specific), then the IBI name, then a
    cleaned-up version. ID-first because Hebrew names don't match the English
    Twelvedata index.
    """
    candidates = [ibi_id]
    if name:
        candidates.append(name)
        cleaned = _clean_hebrew_name(name)
        if cleaned != name:
            candidates.append(cleaned)

    for query in candidates:
        result = _search_twelvedata_once(query)
        if result:
            return result
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
