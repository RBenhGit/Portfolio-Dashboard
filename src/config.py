"""Central configuration — loads .env and defines app-wide constants."""
import os
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
