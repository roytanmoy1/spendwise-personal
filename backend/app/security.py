import hashlib
import hmac
import secrets
from collections import deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

ACCESS_COOKIE = "spendwise_access"
REFRESH_COOKIE = "spendwise_refresh"
SESSION_COOKIE = ACCESS_COOKIE
ACCESS_LENGTH = timedelta(minutes=15)
SESSION_LENGTH = timedelta(days=30)
OTP_LENGTH = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
password_hash = PasswordHash.recommended()


# ponytail: Process-local windows cap one worker; use a shared gateway limiter for replicas.
class WindowRateLimiter:
    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        max_clients: int = 2048,
        clock=monotonic,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self.clock = clock
        self.attempts = {}
        self.lock = Lock()

    def allow(self, client: str) -> bool:
        now = self.clock()
        cutoff = now - self.window_seconds
        with self.lock:
            events = self.attempts.get(client)
            if events is None:
                if len(self.attempts) >= self.max_clients:
                    for previous_client, history in tuple(self.attempts.items()):
                        if not history or history[-1] <= cutoff:
                            del self.attempts[previous_client]
                    if len(self.attempts) >= self.max_clients:
                        return False
                events = deque()
                self.attempts[client] = events
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def issue_access_token(
    user_id: str, session_id: str, secret: str, now: datetime
) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "jti": new_token_id(),
            "typ": "access",
            "iss": "spendwise",
            "aud": "spendwise-client",
            "iat": now,
            "exp": now + ACCESS_LENGTH,
        },
        secret,
        algorithm="HS256",
    )


def issue_refresh_token(
    user_id: str,
    session_id: str,
    token_id: str,
    secret: str,
    expires_at: datetime,
    now: datetime,
) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "sid": session_id,
            "jti": token_id,
            "typ": "refresh",
            "iss": "spendwise",
            "aud": "spendwise-client",
            "iat": now,
            "exp": expires_at,
        },
        secret,
        algorithm="HS256",
    )


def read_token(
    token: str, secret: str, now: datetime, expected_type: str
) -> dict | None:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="spendwise-client",
            issuer="spendwise",
            options={
                "verify_exp": False,
                "require": ["exp", "sub", "sid", "typ", "iss", "aud"],
            },
        )
        if (
            datetime.fromtimestamp(claims["exp"], tz=UTC) <= now
            or claims["typ"] != expected_type
            or claims["iss"] != "spendwise"
            or claims["aud"] != "spendwise-client"
        ):
            return None
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        return None


def otp_hash(code: str, secret: str, user_id: str) -> str:
    return hmac.new(
        secret.encode(), f"{user_id}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def otp_matches(code: str, stored_hash: str, secret: str, user_id: str) -> bool:
    return hmac.compare_digest(otp_hash(code, secret, user_id), stored_hash)


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token_id() -> str:
    return str(uuid4())


def set_auth_cookies(
    response, user_id: str, session_id: str, refresh_token: str, settings, now: datetime
) -> str:
    access_token = issue_access_token(user_id, session_id, settings.jwt_secret, now)
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=int(ACCESS_LENGTH.total_seconds()),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=int(SESSION_LENGTH.total_seconds()),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/auth",
    )
    return access_token


def clear_auth_cookies(response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/auth")
