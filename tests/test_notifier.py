"""Tests for src/input/notifier.py — summary composition and SMTP guards.

build_summary is pure, so the wording is tested directly; send() is tested
with SMTP mocked (no mail is ever sent from the suite).
"""
from unittest.mock import MagicMock, patch

import src.input.notifier as nf
from src.input.notifier import build_summary


class TestBuildSummary:
    def test_success_reports_new_rows(self):
        subject, body = build_summary(
            0, "IBI_x.pdf",
            {"rows_new": 26, "rows_duplicate": 0, "rows_total": 41,
             "rows_quarantined": []},
        )
        assert "26 new rows" in subject
        assert "PROBLEM" not in subject
        assert "IBI_x.pdf" in body
        assert "26 new, 0 duplicate" in body

    def test_singular_row_wording(self):
        subject, _ = build_summary(
            0, "x.pdf", {"rows_new": 1, "rows_quarantined": []})
        assert "1 new row" in subject and "1 new rows" not in subject

    def test_quarantined_rows_are_listed_with_reasons(self):
        # The whole point of the email: a dropped transaction must be visible,
        # not just counted. Previously the quarantine list was discarded.
        subject, body = build_summary(
            0, "x.pdf",
            {"rows_new": 5, "rows_quarantined": [
                {"reason": "no transaction type printed",
                 "raw_chars": "16/08/26 MAIN -1.00"},
            ]},
        )
        assert "1 quarantined" in subject
        assert "no transaction type printed" in body
        assert "16/08/26 MAIN -1.00" in body

    def test_auth_failure_is_flagged_as_problem(self):
        subject, body = build_summary(3, error="IMAP login rejected")
        assert "PROBLEM" in subject
        assert "AUTH FAILED" in body
        assert "IMAP login rejected" in body

    def test_no_new_mail_is_not_a_problem(self):
        subject, body = build_summary(2)
        assert "PROBLEM" not in subject
        assert "no new" in subject.lower()

    def test_ingest_failure_includes_error(self):
        subject, body = build_summary(4, "x.pdf", error="ValueError: boom")
        assert "PROBLEM" in subject
        assert "ValueError: boom" in body


class TestSend:
    @patch("src.input.notifier.smtplib.SMTP")
    def test_sends_via_starttls_and_login(self, mock_smtp, monkeypatch):
        monkeypatch.setattr(nf, "NOTIFY_ENABLED", True)
        monkeypatch.setattr(nf, "SMTP_USER", "u@example.com")
        monkeypatch.setattr(nf, "SMTP_PASSWORD", "pw")
        monkeypatch.setattr(nf, "NOTIFY_TO", "u@example.com")
        conn = MagicMock()
        mock_smtp.return_value.__enter__.return_value = conn

        assert nf.send("subj", "body") is True
        conn.starttls.assert_called_once()
        conn.login.assert_called_once_with("u@example.com", "pw")
        conn.send_message.assert_called_once()

    @patch("src.input.notifier.smtplib.SMTP")
    def test_smtp_failure_never_raises(self, mock_smtp, monkeypatch):
        # A notification failure must not change the import's exit code, or
        # cron would report a healthy import as broken.
        monkeypatch.setattr(nf, "NOTIFY_ENABLED", True)
        monkeypatch.setattr(nf, "SMTP_USER", "u@example.com")
        monkeypatch.setattr(nf, "SMTP_PASSWORD", "pw")
        monkeypatch.setattr(nf, "NOTIFY_TO", "u@example.com")
        mock_smtp.side_effect = OSError("network down")

        assert nf.send("subj", "body") is False

    def test_disabled_does_not_connect(self, monkeypatch):
        monkeypatch.setattr(nf, "NOTIFY_ENABLED", False)
        with patch("src.input.notifier.smtplib.SMTP") as mock_smtp:
            assert nf.send("s", "b") is False
            mock_smtp.assert_not_called()

    def test_missing_credentials_skips(self, monkeypatch):
        monkeypatch.setattr(nf, "NOTIFY_ENABLED", True)
        monkeypatch.setattr(nf, "SMTP_PASSWORD", "")
        with patch("src.input.notifier.smtplib.SMTP") as mock_smtp:
            assert nf.send("s", "b") is False
            mock_smtp.assert_not_called()
