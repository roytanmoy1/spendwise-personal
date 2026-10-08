import hmac
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.email import EmailDeliveryUnavailable
from app.models import (
    AdminNotification,
    AuthSession,
    EmailVerification,
    RefreshToken,
    User,
    new_id,
)
from app.security import (
    OTP_LENGTH,
    REFRESH_COOKIE,
    SESSION_LENGTH,
    clear_auth_cookies,
    generate_otp,
    issue_refresh_token,
    new_token_id,
    otp_hash,
    read_token,
    refresh_hash,
    set_auth_cookies,
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def create_auth_session(db: Session, user: User, settings, response, now: datetime):
    session_id = new_id()
    expires_at = now + SESSION_LENGTH
    auth_session = AuthSession(
        id=session_id,
        user_id=user.id,
        created_at=now,
        expires_at=expires_at,
    )
    token_id = new_token_id()
    refresh_token = issue_refresh_token(
        user.id, session_id, token_id, settings.jwt_secret, expires_at, now
    )
    db.add(auth_session)
    db.add(
        RefreshToken(
            id=token_id,
            session_id=session_id,
            token_hash=refresh_hash(refresh_token),
            expires_at=expires_at,
            created_at=now,
        )
    )
    db.flush()
    db.commit()
    set_auth_cookies(response, user.id, session_id, refresh_token, settings, now)
    return auth_session


def issue_email_verification(
    db: Session,
    user: User,
    settings,
    email_sender,
    now: datetime,
    password_reset_hash: str | None = None,
) -> None:
    current = db.scalar(
        select(EmailVerification).where(EmailVerification.user_id == user.id)
    )
    if current is not None:
        db.delete(current)
        db.flush()
    code = generate_otp()
    db.add(
        EmailVerification(
            user_id=user.id,
            code_hash=otp_hash(code, settings.jwt_secret, user.id),
            password_reset_hash=password_reset_hash,
            expires_at=now + OTP_LENGTH,
            attempts=0,
            created_at=now,
        )
    )
    db.commit()
    try:
        email_sender(
            user.email,
            "Your SpendWise verification code",
            f"Your SpendWise verification code is {code}. It expires in 10 minutes. If you did not request it, ignore this email.",
        )
    except EmailDeliveryUnavailable:
        db.query(EmailVerification).filter_by(user_id=user.id).delete()
        db.commit()
        raise


def notify_pending_access(
    db: Session, user: User, settings, email_sender, now: datetime
) -> None:
    admin_emails = {settings.superadmin_email.casefold()}
    admin_emails.update(
        email.casefold()
        for email in db.scalars(
            select(User.email).where(
                User.role.in_(("admin", "superadmin")), User.status == "active"
            )
        )
    )
    admin_emails.discard(user.email.casefold())
    for admin_email in admin_emails:
        db.add(
            AdminNotification(
                recipient_email=admin_email,
                applicant_user_id=user.id,
                applicant_email=user.email,
                event="access_requested",
                created_at=now,
            )
        )
    db.commit()
    body = f"{user.name} ({user.email}) verified their email and is waiting for a SpendWise role assignment."
    for admin_email in admin_emails:
        try:
            email_sender(admin_email, "SpendWise access approval requested", body)
        except EmailDeliveryUnavailable:
            continue


def rotate_refresh_token(request, response, engine, settings, now: datetime) -> bool:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    claims = (
        read_token(raw_token, settings.jwt_secret, now, "refresh")
        if raw_token
        else None
    )
    if claims is None:
        clear_auth_cookies(response)
        return False

    with Session(engine, expire_on_commit=False) as db:
        token = db.scalar(
            select(RefreshToken)
            .where(RefreshToken.id == claims.get("jti"))
            .with_for_update()
        )
        if token is None or not hmac.compare_digest(
            token.token_hash, refresh_hash(raw_token)
        ):
            clear_auth_cookies(response)
            return False

        auth_session = db.get(AuthSession, token.session_id)
        user = db.get(User, claims["sub"])
        token_expired = _utc(token.expires_at) <= now
        if auth_session is None or user is None:
            clear_auth_cookies(response)
            return False
        if token.used_at is not None:
            auth_session.revoked_at = now
            db.commit()
            clear_auth_cookies(response)
            return False
        if (
            token_expired
            or auth_session.revoked_at is not None
            or _utc(auth_session.expires_at) <= now
            or user.status == "suspended"
            or not user.email_verified
        ):
            auth_session.revoked_at = now
            db.commit()
            clear_auth_cookies(response)
            return False

        next_id = new_token_id()
        next_token = issue_refresh_token(
            user.id,
            auth_session.id,
            next_id,
            settings.jwt_secret,
            auth_session.expires_at,
            now,
        )
        token.used_at = now
        token.replaced_by_id = next_id
        db.add(
            RefreshToken(
                id=next_id,
                session_id=auth_session.id,
                token_hash=refresh_hash(next_token),
                expires_at=auth_session.expires_at,
                created_at=now,
            )
        )
        db.commit()
        set_auth_cookies(response, user.id, auth_session.id, next_token, settings, now)
        return True


def revoke_refresh_session(request, db: Session, settings, now: datetime) -> None:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    claims = (
        read_token(raw_token, settings.jwt_secret, now, "refresh")
        if raw_token
        else None
    )
    if claims is None:
        return
    token = db.get(RefreshToken, claims.get("jti"))
    if token is None or not hmac.compare_digest(
        token.token_hash, refresh_hash(raw_token)
    ):
        return
    auth_session = db.get(AuthSession, token.session_id)
    if auth_session is not None and auth_session.revoked_at is None:
        auth_session.revoked_at = now
