"""Read IBI broker Excel → sorted DataFrame + SHA256 row_hash per row."""
import hashlib
from pathlib import Path
from typing import Union

import pandas as pd

COLUMN_MAP = {
    "תאריך":                    "date",
    "סוג פעולה":                 "transaction_type",
    "שם נייר":                   "security_name",
    "מס' נייר / סימבול":         "security_symbol",
    "כמות":                      "quantity",
    "שער ביצוע":                 "execution_price_raw",
    "מטבע":                      "currency",
    "עמלת פעולה":                "commission",
    "עמלות נלוות":               "additional_fees",
    'תמורה במט"ח':               "amount_foreign_currency",
    "תמורה בשקלים":              "amount_local_currency",
    "יתרה שקלית":                "balance",
    "אומדן מס רווחי הון":        "capital_gains_tax_estimate",
}

_NUMERIC_COLS = [
    "quantity", "execution_price_raw", "commission", "additional_fees",
    "amount_foreign_currency", "amount_local_currency",
    "balance", "capital_gains_tax_estimate",
]


def read_excel(path: Union[str, Path]) -> pd.DataFrame:
    """Read IBI Excel, normalize columns, sort ASC, add row_hash."""
    df = pd.read_excel(str(path), engine="openpyxl", dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=COLUMN_MAP)

    # Parse DD/MM/YYYY → YYYY-MM-DD
    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["date"])
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    # Sort oldest first (IBI exports newest first)
    df = df.sort_values("date", ascending=True).reset_index(drop=True)

    # Normalize
    df["currency"] = df["currency"].str.strip()
    df["security_symbol"] = df["security_symbol"].astype(str).str.strip()

    # Row hash (SHA256 of all values joined)
    def _hash(row: pd.Series) -> str:
        return hashlib.sha256("|".join(str(v) for v in row.values).encode()).hexdigest()

    df["row_hash"] = df.apply(_hash, axis=1)

    # Convert numerics
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def iter_rows(df: pd.DataFrame):
    """Yield each row as a dict."""
    for _, row in df.iterrows():
        yield row.to_dict()
