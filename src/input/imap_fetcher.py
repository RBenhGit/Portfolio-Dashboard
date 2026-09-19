"""Fetch the latest IBI account-report PDF from Gmail over IMAP.

Auth is an app password over TLS (requires 2-Step Verification on the
account). OAuth was tried first and abandoned: a consumer Gmail account
cannot mark its Cloud project Internal, and a Testing-status consent screen
revokes refresh tokens every 7 days, which unattended cron cannot survive.
An app password does not expire and needs no browser.

Config from .env: IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_APP_PASSWORD,
IMAP_MAILBOX, IMAP_SEARCH_SENDER, IMAP_SEARCH_SUBJECT.
"""
import email
import imaplib
import logging
from email.header import decode_header, make_header
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV = dotenv_values(PROJECT_ROOT / ".env")

IMAP_HOST = _ENV.get("IMAP_HOST") or "imap.gmail.com"
IMAP_PORT = int(_ENV.get("IMAP_PORT") or 993)
IMAP_USER = _ENV.get("IMAP_USER") or ""
IMAP_APP_PASSWORD = _ENV.get("IMAP_APP_PASSWORD") or ""
IMAP_MAILBOX = _ENV.get("IMAP_MAILBOX") or "INBOX"

# Gmail's search grammar (from:/subject:/has:attachment) has no IMAP
# equivalent, so the query is split: IMAP SEARCH narrows by sender and
# subject, then attachment filtering happens in Python where it is reliable.
#
# An empty IMAP_SEARCH_SENDER means "any sender" and must be honoured: the
# reports arrive direct from itrademail@ibi.co.il, but one month came as a
# forward from a personal address, so pinning either one drops the other.
# `or` would substitute the default here and make that unconfigurable.
_sender = _ENV.get("IMAP_SEARCH_SENDER")
SEARCH_SENDER = _sender if _sender is not None else "itrademail@ibi.co.il"
SEARCH_SUBJECT = _ENV.get("IMAP_SEARCH_SUBJECT") or "דיווח לחודש"

DEFAULT_OUT_DIR = PROJECT_ROOT / "Trans_Input" / "pdf_archive"


class ImapAuthError(Exception):
    """Raised when IMAP auth is unavailable or rejected (missing app
    password, or the server refused the credentials)."""


class ImapAccountMismatch(Exception):
    """Raised when the configured IMAP user is not the expected account."""


EXPECTED_ACCOUNT = _ENV.get("IMAP_EXPECTED_ACCOUNT") or IMAP_USER


def _decode(value: Optional[str]) -> str:
    """Decode an RFC 2047 encoded-word header (Hebrew subjects arrive
    base64-encoded) into plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _connect():
    """Open an authenticated IMAP connection. Raises ImapAuthError."""
    if not IMAP_APP_PASSWORD:
        raise ImapAuthError(
            "no IMAP_APP_PASSWORD in .env; create one at "
            "https://myaccount.google.com/apppasswords"
        )
    if not IMAP_USER:
        raise ImapAuthError("no IMAP_USER in .env")
    if EXPECTED_ACCOUNT and IMAP_USER.lower() != EXPECTED_ACCOUNT.lower():
        raise ImapAccountMismatch(
            f"expected {EXPECTED_ACCOUNT}, .env configures {IMAP_USER}"
        )

    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    except OSError as exc:
        raise ImapAuthError(f"cannot reach {IMAP_HOST}:{IMAP_PORT}: {exc}") from exc

    try:
        conn.login(IMAP_USER, IMAP_APP_PASSWORD)
    except imaplib.IMAP4.error as exc:
        # Gmail returns AUTHENTICATIONFAILED for a bad/revoked app password
        # and for an account without 2FA.
        raise ImapAuthError(f"IMAP login rejected for {IMAP_USER}: {exc}") from exc

    logger.info("IMAP connected as %s", IMAP_USER)
    return conn


def _search_raw(conn):
    """Issue the SEARCH, handling a non-ASCII subject.

    imaplib encodes command arguments as ASCII, so a Hebrew subject raises
    UnicodeEncodeError before the command is sent -- passing CHARSET UTF-8
    only tells the *server* what to expect. The subject therefore goes as a
    literal via conn.literal, which imaplib sends as raw bytes.
    """
    if SEARCH_SUBJECT:
        try:
            # conn.literal consumes one literal per command, so the subject
            # must be the final argument.
            args = ["CHARSET", "UTF-8"]
            if SEARCH_SENDER:
                args += ["FROM", f'"{SEARCH_SENDER}"']
            args += ["SUBJECT"]
            conn.literal = SEARCH_SUBJECT.encode("utf-8")
            typ, _ = conn._simple_command("SEARCH", *args)
            # _simple_command returns the command completion line, not the
            # ids; the matches arrive in the untagged SEARCH response.
            return conn._untagged_response(typ, [None], "SEARCH")
        except (imaplib.IMAP4.error, UnicodeError) as exc:
            logger.warning(
                "UTF-8 subject search failed (%s); falling back to sender-only "
                "search and filtering subjects in Python", exc
            )
            conn.literal = None

    # No subject term, or the UTF-8 search was rejected.
    if SEARCH_SENDER:
        return conn.search(None, "FROM", f'"{SEARCH_SENDER}"')
    return conn.search(None, "ALL")


def _search_ids(conn) -> list:
    """Return message ids matching sender+subject, oldest-first per IMAP."""
    status, _ = conn.select(IMAP_MAILBOX, readonly=True)
    if status != "OK":
        raise ImapAuthError(f"cannot select mailbox {IMAP_MAILBOX!r}")

    status, data = _search_raw(conn)
    if status != "OK":
        return []
    ids = data[0].split() if data and data[0] else []
    logger.info(
        "IMAP search FROM=%r SUBJECT=%r -> %d message(s)",
        SEARCH_SENDER, SEARCH_SUBJECT, len(ids),
    )
    return ids


def fetch_latest_report(
    out_dir: Path = DEFAULT_OUT_DIR,
    interactive: bool = False,
) -> Optional[Path]:
    """Fetch the newest matching PDF attachment from Gmail over IMAP.

    Returns the path to the saved PDF, or None if no matching mail was
    found. Raises ImapAuthError if auth is unavailable and
    ImapAccountMismatch if .env points at the wrong account.

    `interactive` is accepted and ignored: IMAP never needs browser consent.
    It exists so callers (and cron) can pass it uniformly.
    """
    conn = _connect()
    try:
        ids = _search_ids(conn)
        if not ids:
            return None

        # IMAP returns ascending ids; newest last. Walk newest-first and take
        # the first message that actually carries a PDF.
        for msg_id in reversed(ids):
            status, data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                continue
            msg = email.message_from_bytes(data[0][1])
            subject = _decode(msg.get("Subject"))

            # The sender-only fallback cannot filter by subject server-side,
            # so re-check here; the decoded header is what we compare against.
            if SEARCH_SUBJECT and SEARCH_SUBJECT not in subject:
                logger.debug("Skipping %r: subject does not match", subject)
                continue

            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                filename = _decode(part.get_filename())
                if not filename.lower().endswith(".pdf"):
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                out_dir_p = Path(out_dir)
                out_dir_p.mkdir(parents=True, exist_ok=True)
                # Strip any path separators a crafted filename might carry.
                out_path = out_dir_p / Path(filename).name
                out_path.write_bytes(payload)
                logger.info(
                    "Fetched %s (%d bytes) from message %s (%r)",
                    out_path, len(payload), msg_id.decode(errors="replace"), subject,
                )
                return out_path

        logger.info("No message with a PDF attachment among %d match(es)", len(ids))
        return None
    finally:
        try:
            conn.logout()
        except Exception:
            pass
