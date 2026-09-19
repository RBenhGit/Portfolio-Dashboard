#!/usr/bin/env python3
"""Fetch the latest IBI PDF report from Gmail over IMAP and ingest it.

Run:
    venv/bin/python scripts/run_import.py

Exit codes (mirrors scripts/gmail_fetch_probe.py's contract):
    0 = new PDF fetched and ingested
    2 = authed but no new/matching mail
    3 = auth unavailable (missing or rejected IMAP app password)
    4 = ingestion failed after a successful fetch
"""
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_import")


def main() -> int:
    import traceback

    from dotenv import dotenv_values
    from src.input.imap_fetcher import (
        fetch_latest_report, ImapAuthError, ImapAccountMismatch)
    from src.input import notifier

    env = dotenv_values(PROJECT_ROOT / ".env")
    pdf_password = env.get("IBI_PDF_PASSWORD")

    try:
        pdf_path = fetch_latest_report(interactive=False)
    except (ImapAuthError, ImapAccountMismatch) as exc:
        # Exit 3 rather than a traceback so cron can distinguish an auth
        # problem from "no new mail" (2) and a failed ingest (4).
        logger.error("IMAP auth failed: %s", exc)
        notifier.notify(3, error=str(exc))
        return 3

    if pdf_path is None:
        logger.info("No new matching mail found")
        notifier.notify(2)
        return 2

    logger.info("Fetched %s", pdf_path)

    from src.portfolio.ingestion import ingest

    try:
        # skip_build_if_unchanged: a re-fetched PDF that inserts nothing does
        # not need the full ~8-minute rebuild.
        result = ingest(pdf_path, pdf_password=pdf_password,
                        skip_build_if_unchanged=True)
    except Exception:
        logger.exception("Ingestion failed for %s", pdf_path)
        notifier.notify(4, pdf_name=pdf_path.name, error=traceback.format_exc(limit=3))
        return 4

    logger.info(
        "Ingested %s: %d new rows, %d duplicates, %d quarantined",
        pdf_path.name, result["rows_new"], result["rows_duplicate"],
        len(result["rows_quarantined"]),
    )
    if result["rows_quarantined"]:
        logger.warning(
            "%d row(s) need manual review — see src/input/pdf_reader.py's "
            "quarantine format; cross-check against %s directly",
            len(result["rows_quarantined"]), pdf_path.name,
        )
    notifier.notify(0, pdf_name=pdf_path.name, result=result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
