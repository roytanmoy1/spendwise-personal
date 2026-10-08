import pytest
from sqlalchemy import create_engine

from app.config import Settings
from app.main import create_app
from app.security import WindowRateLimiter


def test_window_limiter_expires_attempts_and_bounds_client_storage():
    instant = [100.0]
    limiter = WindowRateLimiter(
        limit=2, window_seconds=60, max_clients=1, clock=lambda: instant[0]
    )

    assert limiter.allow("first") is True
    assert limiter.allow("first") is True
    assert limiter.allow("first") is False
    assert limiter.allow("second") is False

    instant[0] = 161.0
    assert limiter.allow("second") is True


def test_production_requires_a_long_secret_and_https_origin():
    engine = create_engine("sqlite+pysqlite://")
    settings = Settings(
        database_url="postgresql://example.invalid/app?sslmode=require",
        demo_mode=False,
        secure_cookies=True,
        jwt_secret="too-short",
        frontend_origin="http://app.example",
    )
    with pytest.raises(ValueError, match="Production needs"):
        create_app(settings=settings, engine=engine)

    settings.jwt_secret = None
    with pytest.raises(ValueError, match="Production needs"):
        create_app(settings=settings, engine=engine)

    settings.jwt_secret = "a" * 48
    with pytest.raises(ValueError, match="Production needs"):
        create_app(settings=settings, engine=engine)

    settings.frontend_origin = "https://app.example"
    settings.resend_api_key = "test-mail-api-key"
    settings.email_from = "SpendWise <verify@example.com>"
    assert create_app(settings=settings, engine=engine)

    settings.google_client_id = "configured-client"
    with pytest.raises(ValueError, match="Google OAuth"):
        create_app(settings=settings, engine=engine)
