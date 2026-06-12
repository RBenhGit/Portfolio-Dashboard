"""TASE public market-data API — numeric security ID → ticker resolution.

Uses the JSON endpoint behind TASE's own website (market.tase.co.il), which
serves per-security data by security number with no API key:

    GET https://api.tase.co.il/api/company/securitydata?securityId=<id>&lang=1

Response includes "Symbol" (the TASE alphabetic ticker, e.g. "MPP") and
English name fields. Unknown IDs return HTTP 200 with a null body. Browser
User-Agent headers are required — the default python-requests UA is rejected
by TASE's firewall.
"""
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_SECURITY_DATA_URL = "https://api.tase.co.il/api/company/securitydata"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://market.tase.co.il/",
}


def _display_name(data: dict) -> str:
    """Pick the best English display name from the response (title-cased)."""
    raw = data.get("CompanyName") or data.get("SecurityLongName") or data.get("Name") or ""
    raw = str(raw).strip()
    return raw.title() if raw.isupper() else raw


def lookup_security(security_id: str) -> Optional[dict]:
    """Resolve a TASE numeric security id via TASE's public website API.

    Returns {"symbol": "MPP", "name": "More Pension"} or None. No API key
    needed; callers are expected to cache results (symbol_mapper persists to
    the tase_symbol_map table, so each ID hits the network at most once).
    """
    sec_id = str(security_id).strip()
    try:
        resp = requests.get(
            _SECURITY_DATA_URL,
            params={"securityId": sec_id, "lang": "1"},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("TASE API lookup failed for %s: %s", sec_id, exc)
        return None

    if not isinstance(data, dict):  # unknown IDs return null
        return None

    symbol = str(data.get("Symbol") or "").strip()
    if not symbol:
        return None
    return {"symbol": symbol, "name": _display_name(data) or symbol}
