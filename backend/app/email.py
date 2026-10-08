import httpx

from app.config import Settings


class EmailDeliveryUnavailable(Exception):
    pass


def send_email(settings: Settings, recipient: str, subject: str, body: str) -> None:
    if not settings.resend_api_key or not settings.email_from:
        raise EmailDeliveryUnavailable("Email delivery is not configured")
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [recipient],
                    "subject": subject,
                    "text": body,
                },
            )
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as error:
        raise EmailDeliveryUnavailable("Email could not be delivered") from error
