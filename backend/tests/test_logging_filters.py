"""Unit tests for ``app.logging_filters``.

Covers the structured-log secret redaction guard. The CR/LF half of
the same module is already exercised by other tests; the new BYOK
work adds the secret-pattern scrubbing.
"""

from __future__ import annotations

import logging

import pytest

from app.logging_filters import install_log_injection_guard


@pytest.fixture(autouse=True)
def install_guard():
    """Make sure every test in this module runs with the guard installed."""
    install_log_injection_guard()


def _capture(caplog) -> str:
    """Concatenate every captured record's formatted message."""
    return "\n".join(rec.getMessage() for rec in caplog.records)


class TestRedaction:
    def test_anthropic_key_redacted_in_message(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("user supplied sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFFGGGG")
        out = _capture(caplog)
        assert "sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFFGGGG" not in out
        assert "[redacted]" in out

    def test_anthropic_key_redacted_in_args(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("verifying %s", "sk-ant-api03-XXXXYYYYZZZZWWWW00001111")
        out = _capture(caplog)
        assert "sk-ant-api03-XXXXYYYYZZZZWWWW00001111" not in out
        assert "[redacted]" in out

    def test_bearer_token_redacted(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("got header Bearer eyJabc123_long_enough_token_value")
        out = _capture(caplog)
        assert "eyJabc123_long_enough_token_value" not in out
        assert "[redacted]" in out

    def test_api_key_assignment_redacted(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("config: api_key=AbCdEfGh1234567890")
        out = _capture(caplog)
        assert "AbCdEfGh1234567890" not in out
        assert "[redacted]" in out

    def test_x_api_key_header_redacted(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("headers: X-API-Key: secret_value_99999999")
        out = _capture(caplog)
        assert "secret_value_99999999" not in out
        assert "[redacted]" in out

    def test_password_assignment_redacted(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("login attempt password=hunter2pw9")
        out = _capture(caplog)
        assert "hunter2pw9" not in out
        assert "[redacted]" in out

    def test_innocuous_message_passes_through(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("hello world from user 42")
        out = _capture(caplog)
        # Loose matching can produce false positives; assert the
        # innocuous case is left intact so day-to-day logs aren't
        # mangled.
        assert "hello world from user 42" in out

    def test_dict_args_redacted(self, caplog):
        caplog.set_level(logging.INFO)
        logging.getLogger("test").info("ctx %(key)s", {"key": "sk-ant-api03-DICT_VARIANT_LONGTOKEN"})
        out = _capture(caplog)
        assert "sk-ant-api03-DICT_VARIANT_LONGTOKEN" not in out
        assert "[redacted]" in out


class TestNoTokenInLogs:
    """Regression test against the BYOK plaintext token leaking via logs."""

    def test_loose_token_text_is_redacted(self, caplog):
        # A future contributor might print a header dict verbatim;
        # confirm the redaction catches a plausible Anthropic key
        # value before it reaches any handler.
        token = "sk-ant-api03-Z1234567890abcdefghijklmn"
        caplog.set_level(logging.DEBUG)
        logging.getLogger("test").debug("request headers = %r", {"x-api-key": token, "user-agent": "x"})
        out = _capture(caplog)
        assert token not in out
