from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///./spendwise.db"
    jwt_secret: str | None = None
    demo_mode: bool = True
    frontend_origin: str = "http://127.0.0.1:5173"
    secure_cookies: bool = False
    graphql_requests_per_minute: int = Field(default=120, ge=1, le=5000)
    auth_attempts_per_minute: int = Field(default=10, ge=1, le=100)
    otp_attempts_per_minute: int = Field(default=5, ge=1, le=30)
    resend_api_key: str | None = None
    email_from: str | None = None
    superadmin_email: str = "roytanmoy.main@gmail.com"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
