"""Tests for src/input/imap_fetcher.py — mocked IMAP, no real network/login."""
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

import src.input.imap_fetcher as imf
from src.input.imap_fetcher import (
    fetch_latest_report,
    ImapAuthError,
    ImapAccountMismatch,
)


def _message_with_pdf(filename="report.pdf", data=b"%PDF-fake", subject="דיווח לחודש יולי"):
    msg = EmailMessage()
    msg["From"] = "ran@benhur.co"
    msg["Subject"] = subject
    msg.set_content("see attached")
    msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    return msg.as_bytes()


def _message_without_pdf():
    msg = EmailMessage()
    msg["From"] = "ran@benhur.co"
    msg["Subject"] = "no attachment here"
    msg.set_content("body only")
    return msg.as_bytes()


def _mock_conn(ids=(b"1",), raw_by_id=None):
    """Build a MagicMock standing in for an IMAP4_SSL connection."""
    conn = MagicMock()
    conn.select.return_value = ("OK", [b"1"])
    result = ("OK", [b" ".join(ids)] if ids else [b""])
    conn.search.return_value = result
    # The non-ASCII subject path issues _simple_command and then reads the
    # ids out of the untagged SEARCH response.
    conn._simple_command.return_value = ("OK", [b"SEARCH completed"])
    conn._untagged_response.return_value = result

    raw_by_id = raw_by_id or {}

    def fetch(msg_id, spec):
        raw = raw_by_id.get(msg_id)
        if raw is None:
            return ("NO", [None])
        return ("OK", [(b"header", raw)])

    conn.fetch.side_effect = fetch
    return conn


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    """Give every test valid-looking credentials unless it overrides them."""
    monkeypatch.setattr(imf, "IMAP_USER", "rbh.home.il@gmail.com")
    monkeypatch.setattr(imf, "EXPECTED_ACCOUNT", "rbh.home.il@gmail.com")
    monkeypatch.setattr(imf, "IMAP_APP_PASSWORD", "fake-app-password")


class TestAuth:
    def test_missing_app_password_raises(self, monkeypatch):
        monkeypatch.setattr(imf, "IMAP_APP_PASSWORD", "")
        with pytest.raises(ImapAuthError, match="app password|APP_PASSWORD"):
            fetch_latest_report()

    def test_account_mismatch_raises(self, monkeypatch):
        monkeypatch.setattr(imf, "IMAP_USER", "someone.else@gmail.com")
        with pytest.raises(ImapAccountMismatch):
            fetch_latest_report()

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_login_failure_raises_auth_error(self, mock_ssl):
        import imaplib as _imaplib

        conn = MagicMock()
        conn.login.side_effect = _imaplib.IMAP4.error("AUTHENTICATIONFAILED")
        mock_ssl.return_value = conn

        with pytest.raises(ImapAuthError, match="rejected"):
            fetch_latest_report()


class TestFetchLatestReport:
    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_no_matching_messages_returns_none(self, mock_ssl, tmp_path):
        mock_ssl.return_value = _mock_conn(ids=())
        assert fetch_latest_report(out_dir=tmp_path) is None

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_fetches_and_saves_pdf(self, mock_ssl, tmp_path):
        raw = _message_with_pdf(filename="IBI_report.pdf", data=b"%PDF-1.4 real")
        mock_ssl.return_value = _mock_conn(ids=(b"1",), raw_by_id={b"1": raw})

        result = fetch_latest_report(out_dir=tmp_path)

        assert result is not None
        assert result.name == "IBI_report.pdf"
        assert result.read_bytes() == b"%PDF-1.4 real"

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_message_without_pdf_skipped(self, mock_ssl, tmp_path):
        mock_ssl.return_value = _mock_conn(
            ids=(b"1",), raw_by_id={b"1": _message_without_pdf()}
        )
        assert fetch_latest_report(out_dir=tmp_path) is None

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_picks_newest_message(self, mock_ssl, tmp_path):
        """IMAP returns ascending ids; the highest id must win."""
        mock_ssl.return_value = _mock_conn(
            ids=(b"1", b"2"),
            raw_by_id={
                b"1": _message_with_pdf(filename="old.pdf", data=b"%PDF-old"),
                b"2": _message_with_pdf(filename="new.pdf", data=b"%PDF-new"),
            },
        )

        result = fetch_latest_report(out_dir=tmp_path)

        assert result.name == "new.pdf"
        assert result.read_bytes() == b"%PDF-new"

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_falls_back_to_older_message_with_pdf(self, mock_ssl, tmp_path):
        """Newest match has no PDF, so the next one down is used."""
        mock_ssl.return_value = _mock_conn(
            ids=(b"1", b"2"),
            raw_by_id={
                b"1": _message_with_pdf(filename="has.pdf", data=b"%PDF-has"),
                b"2": _message_without_pdf(),
            },
        )

        result = fetch_latest_report(out_dir=tmp_path)

        assert result.name == "has.pdf"

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_strips_path_from_attachment_filename(self, mock_ssl, tmp_path):
        raw = _message_with_pdf(filename="../../escape.pdf")
        mock_ssl.return_value = _mock_conn(ids=(b"1",), raw_by_id={b"1": raw})

        result = fetch_latest_report(out_dir=tmp_path)

        assert result.parent == tmp_path
        assert result.name == "escape.pdf"

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_logs_out_even_on_error(self, mock_ssl, tmp_path):
        conn = _mock_conn(ids=(b"1",))
        conn.select.return_value = ("NO", [b""])
        mock_ssl.return_value = conn

        with pytest.raises(ImapAuthError):
            fetch_latest_report(out_dir=tmp_path)

        conn.logout.assert_called_once()


class TestNonAsciiSearch:
    """Regression: imaplib encodes command args as ASCII, so a Hebrew
    SUBJECT term raised UnicodeEncodeError before reaching the server."""

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_hebrew_subject_does_not_raise_unicode_error(self, mock_ssl, tmp_path, monkeypatch):
        monkeypatch.setattr(imf, "SEARCH_SUBJECT", "דיווח לחודש")

        raw = _message_with_pdf(subject="דיווח לחודש יולי 2026")
        conn = _mock_conn(ids=(b"1",), raw_by_id={b"1": raw})
        # Mirror imaplib: a non-ASCII arg passed inline would blow up here.
        conn.search.side_effect = AssertionError(
            "search() called with inline non-ASCII instead of a literal"
        )
        conn._simple_command.return_value = ("OK", [b"1"])
        mock_ssl.return_value = conn

        result = fetch_latest_report(out_dir=tmp_path)

        assert result is not None
        # The subject must be sent as raw UTF-8 bytes via conn.literal.
        assert conn.literal == "דיווח לחודש".encode("utf-8")

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_falls_back_to_sender_search_when_utf8_rejected(self, mock_ssl, tmp_path, monkeypatch):
        import imaplib as _imaplib

        monkeypatch.setattr(imf, "SEARCH_SUBJECT", "דיווח לחודש")
        raw = _message_with_pdf(subject="דיווח לחודש יולי 2026")
        conn = _mock_conn(ids=(b"1",), raw_by_id={b"1": raw})
        conn._simple_command.side_effect = _imaplib.IMAP4.error("BAD charset")
        mock_ssl.return_value = conn

        result = fetch_latest_report(out_dir=tmp_path)

        assert result is not None
        conn.search.assert_called()

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_fallback_filters_non_matching_subject_in_python(self, mock_ssl, tmp_path, monkeypatch):
        """Sender-only fallback must not return unrelated mail from that sender."""
        import imaplib as _imaplib

        monkeypatch.setattr(imf, "SEARCH_SUBJECT", "דיווח לחודש")
        conn = _mock_conn(
            ids=(b"1",),
            raw_by_id={b"1": _message_with_pdf(subject="something unrelated")},
        )
        conn._simple_command.side_effect = _imaplib.IMAP4.error("BAD charset")
        mock_ssl.return_value = conn

        assert fetch_latest_report(out_dir=tmp_path) is None


class TestSenderConfig:
    """An empty IMAP_SEARCH_SENDER means "any sender" and must not be
    overridden by the module default -- reports arrive both direct from IBI
    and, one month, as a forward from a personal address."""

    def test_empty_sender_is_honoured(self, monkeypatch):
        import importlib
        monkeypatch.setitem(imf._ENV, "IMAP_SEARCH_SENDER", "")
        reloaded = importlib.reload(imf)
        try:
            assert reloaded.SEARCH_SENDER == ""
        finally:
            importlib.reload(imf)

    @patch("src.input.imap_fetcher.imaplib.IMAP4_SSL")
    def test_no_sender_term_when_empty(self, mock_ssl, tmp_path, monkeypatch):
        monkeypatch.setattr(imf, "SEARCH_SENDER", "")
        monkeypatch.setattr(imf, "SEARCH_SUBJECT", "דיווח לחודש")
        conn = _mock_conn(
            ids=(b"1",),
            raw_by_id={b"1": _message_with_pdf(subject="דיווח לחודש 08/2026")},
        )
        mock_ssl.return_value = conn

        assert fetch_latest_report(out_dir=tmp_path) is not None
        # FROM must not appear in the SEARCH when no sender is configured.
        args = conn._simple_command.call_args[0]
        assert "FROM" not in args
