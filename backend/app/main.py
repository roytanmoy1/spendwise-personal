from datetime import UTC, datetime
from functools import partial
from secrets import token_urlsafe
from time import monotonic
from urllib.parse import urlencode

from authlib.integrations.base_client.errors import AuthlibBaseError
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from strawberry.fastapi import GraphQLRouter

from app.api.schema import schema
from app.config import Settings
from app.db import make_engine
from app.email import EmailDeliveryUnavailable, send_email
from app.identity import (
    create_auth_session,
    issue_email_verification,
    revoke_refresh_session,
    rotate_refresh_token,
)
from app.models import User
from app.security import WindowRateLimiter


def create_app(
    settings: Settings | None = None,
    engine=None,
    clock=None,
    rate_clock=None,
    email_sender=None,
) -> FastAPI:
    settings = settings or Settings()
    if not settings.demo_mode:
        database_url = make_url(settings.database_url)
        google_configured = any(
            (
                settings.google_client_id,
                settings.google_client_secret,
                settings.google_redirect_uri,
            )
        )
        if (
            database_url.drivername not in {"postgresql", "postgresql+psycopg"}
            or database_url.query.get("sslmode") != "require"
            or not settings.jwt_secret
            or len(settings.jwt_secret) < 32
            or not settings.secure_cookies
            or not settings.frontend_origin.startswith("https://")
            or not settings.resend_api_key
            or not settings.email_from
            or (
                google_configured
                and (
                    not settings.google_client_id
                    or not settings.google_client_secret
                    or not settings.google_redirect_uri
                    or not settings.google_redirect_uri.startswith("https://")
                )
            )
        ):
            raise ValueError(
                "Production needs TLS Postgres, HTTPS origin, a long JWT_SECRET, secure cookies and email delivery; configured Google OAuth also needs an HTTPS callback"
            )
    if not settings.jwt_secret:
        settings.jwt_secret = token_urlsafe(48)
    engine = engine if engine is not None else make_engine(settings.database_url)
    clock = clock or (lambda: datetime.now(UTC))
    rate_clock = rate_clock or monotonic
    request_limiter = WindowRateLimiter(
        limit=settings.graphql_requests_per_minute, window_seconds=60, clock=rate_clock
    )
    auth_limiter = WindowRateLimiter(
        limit=settings.auth_attempts_per_minute, window_seconds=60, clock=rate_clock
    )
    otp_limiter = WindowRateLimiter(
        limit=settings.otp_attempts_per_minute, window_seconds=60, clock=rate_clock
    )
    email_sender = email_sender or partial(send_email, settings)

    application = FastAPI(title="SpendWise API", docs_url=None, redoc_url=None)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.jwt_secret,
        same_site="lax",
        https_only=settings.secure_cookies,
        session_cookie="spendwise_oauth_state",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type"],
    )

    google_oauth = None
    if settings.google_client_id and settings.google_client_secret:
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        google_oauth = oauth.google
    application.state.google_oauth = google_oauth

    @application.middleware("http")
    async def restrict_graphql(request: Request, call_next):
        if request.url.path.startswith("/auth/") and request.method == "POST":
            origin = request.headers.get("origin")
            if origin != settings.frontend_origin:
                return Response(status_code=403)
            try:
                if int(request.headers.get("content-length", "0")) > 8192:
                    return Response(status_code=413)
            except ValueError:
                return Response(status_code=400)
        if request.url.path == "/graphql" and request.method in {"POST", "GET"}:
            if request.method == "GET" and len(request.url.query) > 8192:
                return Response(status_code=413)
            if request.method == "POST":
                try:
                    content_length = int(request.headers.get("content-length", "0"))
                except ValueError:
                    return Response(status_code=400)
                if content_length > 262_144:
                    return Response(status_code=413)
                origin = request.headers.get("origin")
                if (origin and origin != settings.frontend_origin) or (
                    not settings.demo_mode and not origin
                ):
                    return Response(status_code=403)
            client = request.client.host if request.client else "unknown"
            if not request_limiter.allow(client):
                return Response(status_code=429)
        return await call_next(request)

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.post("/auth/refresh")
    async def refresh(request: Request):
        response = Response(status_code=204)
        if not rotate_refresh_token(request, response, engine, settings, clock()):
            response.status_code = 401
        return response

    @application.post("/auth/logout")
    async def logout(request: Request):
        response = Response(status_code=204)
        with Session(engine, expire_on_commit=False) as session:
            revoke_refresh_session(request, session, settings, clock())
            session.commit()
        from app.security import clear_auth_cookies

        clear_auth_cookies(response)
        return response

    @application.get("/auth/google")
    async def google_login(request: Request):
        if google_oauth is None:
            return RedirectResponse(
                f"{settings.frontend_origin}/login?error=google_not_configured"
            )
        redirect_uri = settings.google_redirect_uri or str(
            request.url_for("google_callback")
        )
        return await google_oauth.authorize_redirect(request, redirect_uri)

    @application.get("/auth/google/callback", name="google_callback")
    async def google_callback(request: Request):
        if google_oauth is None:
            return RedirectResponse(f"{settings.frontend_origin}/login?error=google")
        try:
            token = await google_oauth.authorize_access_token(request)
            identity = token.get("userinfo") or await google_oauth.parse_id_token(
                request, token
            )
            google_email = identity.get("email", "")
            if not identity.get("email_verified") or not identity.get("sub"):
                return RedirectResponse(
                    f"{settings.frontend_origin}/login?error=google_email"
                )
            from email_validator import validate_email

            normalized_email = validate_email(
                google_email, check_deliverability=False
            ).normalized.casefold()
            now = clock()
            with Session(engine, expire_on_commit=False) as session:
                user = session.scalar(
                    select(User).where(User.email == normalized_email)
                )
                if user is None:
                    display_name = (
                        identity.get("name") or normalized_email.partition("@")[0]
                    ).strip()[:80]
                    user = User(
                        name=display_name or "SpendWise user",
                        email=normalized_email,
                        persona="Google workspace",
                        google_subject=identity["sub"],
                        role="viewer",
                        status="email_pending",
                        email_verified=False,
                    )
                    session.add(user)
                    session.flush()
                elif user.google_subject not in (None, identity["sub"]):
                    return RedirectResponse(
                        f"{settings.frontend_origin}/login?error=google"
                    )
                else:
                    user.google_subject = identity["sub"]
                if user.status == "suspended":
                    return RedirectResponse(
                        f"{settings.frontend_origin}/login?error=google"
                    )
                session.commit()
                if not user.email_verified:
                    issue_email_verification(session, user, settings, email_sender, now)
                    verify_url = f"{settings.frontend_origin}/verify-email?{urlencode({'email': user.email})}"
                    return RedirectResponse(verify_url)
                response = RedirectResponse(f"{settings.frontend_origin}/")
                create_auth_session(session, user, settings, response, now)
            return response
        except (EmailDeliveryUnavailable, ValueError):
            return RedirectResponse(f"{settings.frontend_origin}/login?error=email")
        except AuthlibBaseError:
            return RedirectResponse(f"{settings.frontend_origin}/login?error=google")

    async def context_getter(request: Request, response: Response):
        return {
            "request": request,
            "response": response,
            "settings": settings,
            "engine": engine,
            "clock": clock,
            "auth_limiter": auth_limiter,
            "otp_limiter": otp_limiter,
            "email_sender": email_sender,
        }

    application.include_router(
        GraphQLRouter(
            schema,
            context_getter=context_getter,
            graphql_ide="graphiql" if settings.demo_mode else None,
        ),
        prefix="/graphql",
    )
    return application


app = create_app()
