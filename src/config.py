"""Central configuration — loads .env and defines app-wide constants."""
import os
import re
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
EXCEL_PATH = BASE_DIR / "Trans_Input" / "Transactions_IBI.xlsx"
DB_PATH    = BASE_DIR / "data" / "portfolio.db"

# ── API keys ──────────────────────────────────────────────────────────────────
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
YFINANCE_ENABLED   = os.getenv("YFINANCE_ENABLED", "true").lower() == "true"

_SECRET_PARAM_RE = re.compile(
    r"((?:apikey|api_key|token|password)=)[^&\s]+", re.IGNORECASE
)


def redact(value) -> str:
    """Strip secrets from text before it reaches a log.

    `requests.HTTPError.__str__` embeds the fully-resolved request URL, so
    logging an exception from a Twelvedata call wrote the API key in
    plaintext -- measured at 623-923 occurrences per import log. Every site
    that logs a request exception passes it through here.

    Redacts both the configured key wherever it appears and any
    `apikey=`/`token=` query parameter, so a future key or endpoint is
    covered without touching the call sites again.
    """
    text = str(value)
    if TWELVEDATA_API_KEY:
        text = text.replace(TWELVEDATA_API_KEY, "<redacted>")
    return _SECRET_PARAM_RE.sub(r"\1<redacted>", text)
