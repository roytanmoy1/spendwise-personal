import httpx
import pytest

from app.config import Settings
from app.email import EmailDeliveryUnavailable, send_email


def test_send_email_uses_configured_resend_sender_and_payload(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, timeout):
            assert timeout == 8.0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr("app.email.httpx.Client", Client)
    settings = Settings(
        resend_api_key="test-key", email_from="SpendWise <verify@example.com>"
    )

    send_email(settings, "user@example.com", "Verify", "Your code is 123456")

    assert calls[0][0] == "https://api.resend.com/emails"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0][1]["json"]["to"] == ["user@example.com"]


def test_send_email_fails_closed_without_credentials():
    with pytest.raises(EmailDeliveryUnavailable, match="not configured"):
        send_email(Settings(), "user@example.com", "Verify", "body")


def test_send_email_translates_provider_network_failure(monkeypatch):
    request = httpx.Request("POST", "https://api.resend.com/emails")

    class Client:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            raise httpx.ConnectError("network unavailable", request=request)

    monkeypatch.setattr("app.email.httpx.Client", Client)
    settings = Settings(
        resend_api_key="test-key", email_from="SpendWise <verify@example.com>"
    )

    with pytest.raises(EmailDeliveryUnavailable, match="could not be delivered"):
        send_email(settings, "user@example.com", "Verify", "body")
