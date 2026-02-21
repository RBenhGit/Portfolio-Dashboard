"""Ingestion pipeline: Excel → classify → FX fetch → dedup insert → build."""
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Union

from src.database import repository
from src.database.db import create_schema
from src.input.excel_reader import read_excel, iter_rows
from src.classifiers.ibi_classifier import IBIClassifier
from src.market.fx_fetcher import fetch_historical_fx
from src.portfolio import builder

logger = logging.getLogger(__name__)
_classifier = IBIClassifier()


def ingest(source: Union[str, Path], trigger: str = "import") -> dict:
    """Full ingestion pipeline for an IBI Excel file.

    Steps:
      1. Read + sort Excel → DataFrame
      2. Classify each row
      3. Fetch FX rates for all unique dates
      4. Backfill fx_rate_on_date and cost_basis_nis
      5. Dedup-insert into DB
      6. Run portfolio builder
      7. Save snapshot

    Returns dict with import stats + portfolio summary.
    """
    create_schema()

    source = Path(source)
    df = read_excel(source)
    rows_total = len(df)
    logger.info("Read %d rows from %s", rows_total, source.name)

    # Classify
    classified: list[dict] = []
    for row in iter_rows(df):
        try:
            result = _classifier.classify(row)
            classified.append(result)
        except Exception as exc:
            logger.warning("Classification error on row %s: %s", row.get("row_hash"), exc)

    # Collect unique dates needing FX rates
    all_dates = sorted({r["date"] for r in classified if r.get("date")})
    existing_fx = repository.get_all_fx_dates()
    missing_dates = [d for d in all_dates if d not in existing_fx]

    if missing_dates:
        logger.info("Fetching FX rates for %d missing dates…", len(missing_dates))
        try:
            rates = fetch_historical_fx(missing_dates)
            if rates:
                repository.upsert_fx_rates(rates)
                logger.info("Stored %d FX rates", len(rates))
        except Exception as exc:
            logger.warning("FX fetch failed: %s — proceeding without some rates", exc)

    # Backfill fx_rate_on_date and cost_basis_nis
    for r in classified:
        date = r.get("date")
        if date:
            fx = repository.get_fx_rate(date)
            r["fx_rate_on_date"] = fx
            # cost_basis_nis: for USD positions use fx; for NIS positions = cost_basis
            cb = r.get("cost_basis") or 0.0
            currency = str(r.get("currency") or "").strip()
            if currency == "$" and fx:
                r["cost_basis_nis"] = cb * fx
            else:
                r["cost_basis_nis"] = cb

    # Insert (dedup by row_hash)
    rows_new, rows_dup = repository.insert_transactions_deduped(classified)
    logger.info("Inserted %d new rows, %d duplicates skipped", rows_new, rows_dup)
    repository.log_import(source.name, rows_total, rows_new, rows_dup)

    # Build portfolio
    portfolio_state = builder.build(trigger=trigger)

    return {
        "rows_total": rows_total,
        "rows_new": rows_new,
        "rows_duplicate": rows_dup,
        "portfolio": portfolio_state,
    }
