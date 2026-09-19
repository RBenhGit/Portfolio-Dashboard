"""Email the outcome of an unattended import run.

Without this the pipeline is silent: run_import.py returns distinct exit
codes (0/2/3/4) and cron's default mail handler is unconfigured with no MTA
installed, so nothing ever reads them. A revoked app password (exit 3) then
looks exactly like a quiet month (exit 2) and the import can stall
indefinitely unnoticed.

Sends over Gmail SMTP with the same app password already used for IMAP, so
no additional credential or service is involved.

Config from .env: IMAP_USER, IMAP_APP_PASSWORD, plus optional
NOTIFY_TO (defaults to IMAP_USER), NOTIFY_ENABLED, SMTP_HOST, SMTP_PORT.
"""
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV = dotenv_values(PROJECT_ROOT / ".env")

SMTP_HOST = _ENV.get("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(_ENV.get("SMTP_PORT") or 587)
SMTP_USER = _ENV.get("IMAP_USER") or ""
SMTP_PASSWORD = _ENV.get("IMAP_APP_PASSWORD") or ""
NOTIFY_TO = _ENV.get("NOTIFY_TO") or SMTP_USER
NOTIFY_ENABLED = (_ENV.get("NOTIFY_ENABLED") or "true").lower() == "true"

# Exit codes from scripts/run_import.py.
_EXIT_MEANING = {
    0: "OK",
    2: "no new mail",
    3: "AUTH FAILED",
    4: "INGEST FAILED",
    5: "already ingested",
}


def build_summary(exit_code: int, pdf_name: Optional[str] = None,
                  result: Optional[dict] = None,
                  error: Optional[str] = None) -> tuple:
    """Return (subject, body) describing a run. Pure -- no I/O, so it is
    testable without SMTP."""
    meaning = _EXIT_MEANING.get(exit_code, f"unknown exit {exit_code}")
    quarantined = (result or {}).get("rows_quarantined") or []

    if exit_code == 0:
        new = (result or {}).get("rows_new", 0)
        headline = f"OK — {new} new row{'s' if new != 1 else ''}"
        if quarantined:
            headline += f", {len(quarantined)} quarantined"
    elif exit_code == 2:
        headline = "no new report"
    elif exit_code == 5:
        # Not a failure, but not a successful import either: IBI has not
        # issued a new report yet, so the newest one in the mailbox is the
        # one already in the database.
        headline = "already ingested — no new report from IBI"
    else:
        headline = f"PROBLEM — {meaning}"

    subject = f"IBI import: {headline}"

    lines = [f"status   : {meaning} (exit {exit_code})"]
    if pdf_name:
        lines.append(f"fetched  : {pdf_name}")
    if result:
        lines.append(
            f"imported : {result.get('rows_new', 0)} new, "
            f"{result.get('rows_duplicate', 0)} duplicate, "
            f"of {result.get('rows_total', 0)} parsed"
        )
    if quarantined:
        lines.append("")
        lines.append(f"QUARANTINED — {len(quarantined)} row(s) NOT imported:")
        for row in quarantined:
            reason = str(row.get("reason", "")).strip()
            raw = str(row.get("raw_chars", ""))[:90]
            lines.append(f"  - {reason}")
            if raw:
                lines.append(f"      {raw}")
        lines.append("")
        lines.append("Review these against the source PDF and enter them by hand.")
    if error:
        lines.append("")
        lines.append("error:")
        lines.append(error)

    return subject, "\n".join(lines)


def send(subject: str, body: str) -> bool:
    """Send the summary. Returns True on success.

    Never raises: a notification failure must not change the import's own
    exit code, or cron would report a healthy import as broken.
    """
    if not NOTIFY_ENABLED:
        logger.info("Notifications disabled (NOTIFY_ENABLED=false)")
        return False
    if not (SMTP_USER and SMTP_PASSWORD and NOTIFY_TO):
        logger.warning("Notification skipped: SMTP credentials not configured")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_TO
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        logger.info("Notification sent to %s", NOTIFY_TO)
        return True
    except Exception as exc:
        logger.warning("Notification failed (import itself was unaffected): %s", exc)
        return False


def notify(exit_code: int, pdf_name: Optional[str] = None,
           result: Optional[dict] = None, error: Optional[str] = None) -> bool:
    subject, body = build_summary(exit_code, pdf_name, result, error)
    return send(subject, body)
