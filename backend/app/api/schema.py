import hashlib
import re
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import uuid4

import strawberry
from email_validator import EmailNotValidError, validate_email
from graphql import GraphQLError
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from strawberry.extensions import MaxTokensLimiter, QueryDepthLimiter
from strawberry.types import Info

OTP_RESPONSE_MESSAGE = (
    "If this account needs verification, instructions have been sent."
)

from app.domain.csv_io import export_transactions, parse_transactions
from app.domain.insights import categorize_merchant, spending_summary
from app.email import EmailDeliveryUnavailable
from app.identity import (
    create_auth_session,
    issue_email_verification,
    notify_pending_access,
    revoke_refresh_session,
)
from app.models import (
    AdminNotification,
    AuthSession,
    Budget,
    EmailVerification,
    Transaction,
    User,
)
from app.security import (
    ACCESS_COOKIE,
    OTP_MAX_ATTEMPTS,
    clear_auth_cookies,
    otp_matches,
    password_hash,
    read_token,
)


@strawberry.enum
class Category(Enum):
    FOOD = "Food"
    GROCERIES = "Groceries"
    HEALTH = "Health"
    TRANSPORT = "Transport"
    BILLS = "Bills"
    ENTERTAINMENT = "Entertainment"
    SHOPPING = "Shopping"
    OTHER = "Other"


@strawberry.enum
class PaymentMethod(Enum):
    UPI = "upi"
    CARD = "card"
    NET_BANKING = "netbanking"
    CASH = "cash"


@strawberry.enum
class UserRole(Enum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


@strawberry.enum
class AccountStatus(Enum):
    EMAIL_PENDING = "email_pending"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"


@strawberry.type
class Viewer:
    id: strawberry.ID
    name: str
    email: str
    persona: str
    role: UserRole
    status: AccountStatus
    email_verified: bool


@strawberry.type
class AuthOutcome:
    authenticated: bool
    requires_verification: bool
    requires_password_setup: bool
    requires_registration: bool
    message: str
    viewer: Viewer | None


@strawberry.type
class AdminUser:
    id: strawberry.ID
    name: str
    email: str
    persona: str
    role: UserRole
    status: AccountStatus
    email_verified: bool
    created_at: datetime


@strawberry.type
class AdminNotice:
    id: strawberry.ID
    applicant_email: str
    event: str
    created_at: datetime
    read: bool


@strawberry.type
class TransactionNode:
    id: strawberry.ID
    merchant: str
    amount_minor: int
    category: Category
    method: PaymentMethod
    occurred_at: datetime
    city: str | None
    note: str | None
    source: str


@strawberry.type
class CategoryAmount:
    category: Category
    amount_minor: int


@strawberry.type
class MethodAmount:
    method: PaymentMethod
    amount_minor: int


@strawberry.type
class MonthAmount:
    month: str
    amount_minor: int


@strawberry.type
class CityAmount:
    city: str
    amount_minor: int


@strawberry.type
class Overview:
    total_spent_minor: int
    this_month_minor: int
    last_month_minor: int
    transaction_count: int
    by_category: list[CategoryAmount]
    by_method: list[MethodAmount]
    monthly: list[MonthAmount]
    by_city: list[CityAmount]


@strawberry.type
class TransactionPage:
    total_count: int
    has_more: bool
    items: list[TransactionNode]


@strawberry.type
class BudgetNode:
    id: strawberry.ID
    month: str
    category: Category
    limit_minor: int
    spent_minor: int


@strawberry.type
class ImportResult:
    imported: int


@strawberry.input
class TransactionInput:
    merchant: str
    amount_minor: int
    method: PaymentMethod
    occurred_at: datetime
    category: Category | None = None
    city: str | None = None
    note: str | None = None


@strawberry.input
class TransactionFilter:
    merchant: str | None = None
    category: Category | None = None
    method: PaymentMethod | None = None
    month: str | None = None


@strawberry.input
class BudgetInput:
    category: Category
    month: str
    limit_minor: int


def _session(context):
    return Session(context["engine"], expire_on_commit=False)


def _auth_user(context, session):
    now = context["clock"]()
    token = context["request"].cookies.get(ACCESS_COOKIE)
    claims = (
        read_token(token, context["settings"].jwt_secret, now, "access")
        if token
        else None
    )
    auth_session = session.get(AuthSession, claims["sid"]) if claims else None
    expires_at = auth_session.expires_at if auth_session else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        claims is None
        or auth_session is None
        or auth_session.user_id != claims["sub"]
        or auth_session.revoked_at is not None
        or expires_at <= now
    ):
        raise GraphQLError("Sign in to continue")
    user = session.get(User, claims["sub"])
    if user is None or not user.email_verified or user.status == "email_pending":
        raise GraphQLError("Verify your email to continue")
    if user.status == "suspended":
        raise GraphQLError("This account is suspended")
    return user, auth_session


def _user(context, session):
    return _auth_user(context, session)[0]


def _writer(context, session):
    user = _user(context, session)
    if user.status == "pending_review":
        raise GraphQLError("Your account is awaiting access approval")
    if user.status != "active" or user.role not in {"editor", "admin", "superadmin"}:
        raise GraphQLError("Your role has read-only access")
    return user


def _admin(context, session):
    user = _user(context, session)
    if user.status != "active" or user.role not in {"admin", "superadmin"}:
        raise GraphQLError("Administrator access is required")
    return user


def _superadmin(context, session):
    user = _admin(context, session)
    if user.role != "superadmin":
        raise GraphQLError("Superadmin access is required")
    return user


def _viewer(user):
    return Viewer(
        id=user.id,
        name=user.name,
        email=user.email,
        persona=user.persona,
        role=UserRole(user.role),
        status=AccountStatus(user.status),
        email_verified=user.email_verified,
    )


def _admin_user(user):
    return AdminUser(
        id=user.id,
        name=user.name,
        email=user.email,
        persona=user.persona,
        role=UserRole(user.role),
        status=AccountStatus(user.status),
        email_verified=user.email_verified,
        created_at=user.created_at,
    )


def _transaction(transaction):
    return TransactionNode(
        id=transaction.id,
        merchant=transaction.merchant,
        amount_minor=transaction.amount_minor,
        category=Category(transaction.category),
        method=PaymentMethod(transaction.method),
        occurred_at=transaction.occurred_at,
        city=transaction.city,
        note=transaction.note,
        source=transaction.source,
    )


def _month_start(month):
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
        if start.strftime("%Y-%m") != month:
            raise ValueError
        return start
    except ValueError as error:
        raise GraphQLError("Month must use YYYY-MM") from error


def _next_month(start):
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)


def _spent_for_budget(session, user_id, month, category):
    start = _month_start(month)
    return session.scalar(
        select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
            Transaction.user_id == user_id,
            Transaction.category == category,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < _next_month(start),
        )
    )


def _budget_node(session, user_id, budget):
    return BudgetNode(
        id=budget.id,
        month=budget.month,
        category=Category(budget.category),
        limit_minor=budget.limit_minor,
        spent_minor=_spent_for_budget(session, user_id, budget.month, budget.category),
    )


def _overview(context):
    with _session(context) as session:
        user = _user(context, session)
        now = context["clock"]()
        # Only the most recent year is materialized; all-time totals stay in SQL.
        transactions = session.execute(
            select(
                Transaction.amount_minor,
                Transaction.category,
                Transaction.method,
                Transaction.occurred_at,
            ).where(
                Transaction.user_id == user.id,
                Transaction.occurred_at >= now - timedelta(days=365),
            )
        ).all()
        summary = spending_summary(transactions, now=now)
        summary["total_spent_minor"] = session.scalar(
            select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(
                Transaction.user_id == user.id, Transaction.occurred_at <= now
            )
        )
        summary["transaction_count"] = session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.user_id == user.id, Transaction.occurred_at <= now
            )
        )
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        city_totals = session.execute(
            select(Transaction.city, func.sum(Transaction.amount_minor))
            .where(
                Transaction.user_id == user.id,
                Transaction.city.is_not(None),
                Transaction.occurred_at >= month_start,
                Transaction.occurred_at <= now,
            )
            .group_by(Transaction.city)
            .order_by(func.sum(Transaction.amount_minor).desc())
            .limit(5)
        ).all()
        return Overview(
            **{
                key: summary[key]
                for key in (
                    "total_spent_minor",
                    "this_month_minor",
                    "last_month_minor",
                    "transaction_count",
                )
            },
            by_category=[
                CategoryAmount(
                    category=Category(item["category"]),
                    amount_minor=item["amount_minor"],
                )
                for item in summary["by_category"]
            ],
            by_method=[
                MethodAmount(
                    method=PaymentMethod(item["method"]),
                    amount_minor=item["amount_minor"],
                )
                for item in summary["by_method"]
            ],
            monthly=[MonthAmount(**item) for item in summary["monthly"]],
            by_city=[
                CityAmount(city=city, amount_minor=amount)
                for city, amount in city_totals
            ],
        )


def _transactions(context, limit, offset, filters):
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise GraphQLError("Choose a page size of 1 to 100 and an offset up to 10000")
    with _session(context) as session:
        user = _user(context, session)
        conditions = [Transaction.user_id == user.id]
        if filters:
            if filters.merchant:
                merchant = filters.merchant.strip()
                if len(merchant) > 80:
                    raise GraphQLError("Search must be 80 characters or less")
                escaped = (
                    merchant.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                conditions.append(
                    Transaction.merchant.ilike(f"%{escaped}%", escape="\\")
                )
            if filters.category:
                conditions.append(Transaction.category == filters.category.value)
            if filters.method:
                conditions.append(Transaction.method == filters.method.value)
            if filters.month:
                start = _month_start(filters.month)
                conditions.extend(
                    (
                        Transaction.occurred_at >= start,
                        Transaction.occurred_at < _next_month(start),
                    )
                )
        count = session.scalar(select(func.count(Transaction.id)).where(*conditions))
        rows = session.scalars(
            select(Transaction)
            .where(*conditions)
            .order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return TransactionPage(
            total_count=count,
            has_more=offset + len(rows) < count,
            items=[_transaction(row) for row in rows],
        )


def _budgets(context, month):
    with _session(context) as session:
        user = _user(context, session)
        selected = month or context["clock"]().strftime("%Y-%m")
        _month_start(selected)
        budgets = session.scalars(
            select(Budget).where(Budget.user_id == user.id, Budget.month == selected)
        ).all()
        return [_budget_node(session, user.id, budget) for budget in budgets]


def _limit_auth(context):
    request = context["request"]
    client = request.client.host if request.client else "unknown"
    if not context["auth_limiter"].allow(client):
        raise GraphQLError("Too many attempts. Try again later.")


def _limit_otp(context):
    request = context["request"]
    client = request.client.host if request.client else "unknown"
    email_key = context.get("otp_email_key")
    if not context["otp_limiter"].allow(f"ip:{client}") or (
        email_key and not context["otp_limiter"].allow(f"email:{email_key}")
    ):
        raise GraphQLError("Too many verification attempts. Try again later.")


def _normalize_email(email):
    try:
        return validate_email(email, check_deliverability=False).normalized.casefold()
    except EmailNotValidError as error:
        raise GraphQLError("Enter a valid email address") from error


def _persona(value):
    persona = (value or "Personal").strip()
    if not 1 <= len(persona) <= 80:
        raise GraphQLError("Persona must be 1 to 80 characters")
    return persona


def _auth_outcome(
    user=None,
    *,
    requires_verification=False,
    requires_password_setup=False,
    requires_registration=False,
    message="",
):
    return AuthOutcome(
        authenticated=user is not None,
        requires_verification=requires_verification,
        requires_password_setup=requires_password_setup,
        requires_registration=requires_registration,
        message=message,
        viewer=_viewer(user) if user is not None else None,
    )


def _send_verification(
    context,
    session,
    user,
    password_reset_hash=None,
    requires_password_setup=False,
):
    context["otp_email_key"] = hashlib.sha256(
        user.email.casefold().encode()
    ).hexdigest()
    _limit_otp(context)
    try:
        issue_email_verification(
            session,
            user,
            context["settings"],
            context["email_sender"],
            context["clock"](),
            password_reset_hash=password_reset_hash,
        )
    except EmailDeliveryUnavailable as error:
        settings = context["settings"]
        if settings.demo_mode and (
            not settings.resend_api_key or not settings.email_from
        ):
            raise GraphQLError(
                "Email sign-in isn't configured. Configure Resend in the backend "
                "environment to enable email verification."
            ) from error
        raise GraphQLError(
            "Email verification is temporarily unavailable. Try again later."
        ) from error
    return _auth_outcome(
        requires_verification=True,
        requires_password_setup=requires_password_setup,
        message=OTP_RESPONSE_MESSAGE,
    )


def _new_user_name(email):
    return (
        email.partition("@")[0].replace(".", " ").replace("_", " ").strip().title()
        or "SpendWise user"
    )[:80]


def _demo_session(context):
    if not context["settings"].demo_mode:
        raise GraphQLError("Demo is disabled")
    _limit_auth(context)
    with _session(context) as session:
        user = User(
            name="Demo account",
            email=f"demo-{uuid4().hex}@spendwise.invalid",
            persona="Sample workspace",
            role="editor",
            status="active",
            email_verified=True,
        )
        session.add(user)
        session.flush()
        samples = (
            ("Cafe Mellow", 38500, "upi", "Bengaluru"),
            ("Big Bazaar", 129900, "card", "Bengaluru"),
            ("Uber Ride", 28400, "upi", "Bengaluru"),
            ("Apollo Pharmacy", 47200, "card", "Mumbai"),
            ("Kirana Corner", 68500, "cash", "Bengaluru"),
            ("Airtel Broadband", 99900, "netbanking", "Pune"),
            ("Zomato Order", 56000, "upi", "Bengaluru"),
            ("Petrol Pump", 180000, "card", "Mumbai"),
            ("Spotify", 11900, "card", "Pune"),
            ("Amazon Shopping", 215000, "upi", "Bengaluru"),
            ("Metro Fare", 4500, "upi", "Mumbai"),
            ("Restaurant Soma", 78000, "card", "Pune"),
        )
        now = context["clock"]()
        for index, (merchant, amount, method, city) in enumerate(samples * 3):
            session.add(
                Transaction(
                    user_id=user.id,
                    merchant=merchant,
                    amount_minor=amount,
                    category=categorize_merchant(merchant),
                    method=method,
                    occurred_at=now - timedelta(days=index * 2 + 1),
                    city=city,
                    source="demo",
                )
            )
        session.commit()
        create_auth_session(
            session, user, context["settings"], context["response"], now
        )
        return _viewer(user)


def _register(context, name, email, password, persona):
    _limit_auth(context)
    name = name.strip()
    if not 1 <= len(name) <= 80 or not 12 <= len(password) <= 128:
        raise GraphQLError("Enter a name and a password of at least 12 characters")
    normalized_email = _normalize_email(email)
    with _session(context) as session:
        existing_user = session.scalar(
            select(User).where(User.email == normalized_email)
        )
        if existing_user is not None:
            if existing_user.status == "suspended":
                return _auth_outcome(
                    requires_verification=True,
                    message=OTP_RESPONSE_MESSAGE,
                )
            return _send_verification(context, session, existing_user)
        user = User(
            name=name,
            email=normalized_email,
            password_hash=password_hash.hash(password),
            persona=_persona(persona),
            role="viewer",
            status="email_pending",
            email_verified=False,
        )
        session.add(user)
        session.flush()
        return _send_verification(context, session, user)


def _login(context, email, password, persona):
    _limit_auth(context)
    normalized_email = _normalize_email(email)
    with _session(context) as session:
        user = session.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            return _auth_outcome(
                requires_registration=True,
                message="Create an account to continue.",
            )
        if len(password) < 12 or len(password) > 128:
            raise GraphQLError("Invalid credentials")
        if user.status == "suspended":
            return _auth_outcome(
                requires_verification=True,
                requires_password_setup=True,
                message=OTP_RESPONSE_MESSAGE,
            )
        if user.password_hash is None:
            user.password_hash = password_hash.hash(password)
            session.flush()
            return _send_verification(
                context,
                session,
                user,
                password_reset_hash=user.password_hash,
                requires_password_setup=True,
            )
        try:
            password_matches = password_hash.verify(password, user.password_hash)
        except UnknownHashError:
            return _send_verification(
                context,
                session,
                user,
                password_reset_hash=password_hash.hash(password),
                requires_password_setup=True,
            )
        if not password_matches:
            return _send_verification(
                context,
                session,
                user,
                password_reset_hash=password_hash.hash(password),
                requires_password_setup=True,
            )
        if (
            not user.email_verified
            or user.status == "email_pending"
            or not user.password_hash
        ):
            return _send_verification(
                context,
                session,
                user,
                password_reset_hash=password_hash.hash(password),
                requires_password_setup=True,
            )
        create_auth_session(
            session, user, context["settings"], context["response"], context["clock"]()
        )
        return _auth_outcome(user, message="Signed in")


def _verify_email(context, email, code):
    normalized_email = _normalize_email(email)
    context["otp_email_key"] = hashlib.sha256(normalized_email.encode()).hexdigest()
    _limit_otp(context)
    if not re.fullmatch(r"\d{6}", code):
        raise GraphQLError("Invalid or expired verification code")
    now = context["clock"]()
    with _session(context) as session:
        user = session.scalar(select(User).where(User.email == normalized_email))
        challenge = (
            session.scalar(
                select(EmailVerification)
                .where(EmailVerification.user_id == user.id)
                .with_for_update()
            )
            if user
            else None
        )
        if user is None or challenge is None:
            raise GraphQLError("Invalid or expired verification code")
        expires_at = challenge.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now or challenge.attempts >= OTP_MAX_ATTEMPTS:
            session.delete(challenge)
            session.commit()
            raise GraphQLError("Invalid or expired verification code")
        if not otp_matches(
            code, challenge.code_hash, context["settings"].jwt_secret, user.id
        ):
            challenge.attempts += 1
            if challenge.attempts >= OTP_MAX_ATTEMPTS:
                session.delete(challenge)
            session.commit()
            raise GraphQLError("Invalid or expired verification code")

        if challenge.password_reset_hash:
            user.password_hash = challenge.password_reset_hash
        session.delete(challenge)
        user.email_verified = True
        if user.email == context["settings"].superadmin_email.strip().casefold():
            user.role = "superadmin"
            user.status = "active"
        elif user.status == "email_pending":
            user.role = "viewer"
            user.status = "pending_review"
        session.commit()
        if user.status == "pending_review":
            notify_pending_access(
                session, user, context["settings"], context["email_sender"], now
            )
        create_auth_session(
            session, user, context["settings"], context["response"], now
        )
        return _viewer(user)


def _resend_verification(context, email):
    _limit_auth(context)
    normalized_email = _normalize_email(email)
    with _session(context) as session:
        user = session.scalar(select(User).where(User.email == normalized_email))
        challenge = (
            session.scalar(
                select(EmailVerification).where(EmailVerification.user_id == user.id)
            )
            if user is not None and user.status != "suspended"
            else None
        )
        if challenge is not None:
            _send_verification(
                context,
                session,
                user,
                password_reset_hash=challenge.password_reset_hash,
                requires_password_setup=challenge.password_reset_hash is not None,
            )
        return True


def _update_profile(context, name, persona):
    name = name.strip()
    if not 1 <= len(name) <= 80:
        raise GraphQLError("Name must be 1 to 80 characters")
    with _session(context) as session:
        user = _user(context, session)
        user.name = name
        user.persona = _persona(persona)
        session.commit()
        return _viewer(user)


def _pending_users(context):
    with _session(context) as session:
        _admin(context, session)
        users = session.scalars(
            select(User)
            .where(User.email_verified.is_(True), User.status == "pending_review")
            .order_by(User.created_at.asc())
            .limit(500)
        ).all()
        return [_admin_user(user) for user in users]


def _managed_users(context):
    with _session(context) as session:
        _superadmin(context, session)
        users = session.scalars(
            select(User)
            .where(User.role != "superadmin")
            .order_by(User.created_at.desc())
            .limit(500)
        ).all()
        return [_admin_user(user) for user in users]


def _admin_notifications(context):
    with _session(context) as session:
        admin = _admin(context, session)
        notifications = session.scalars(
            select(AdminNotification)
            .where(AdminNotification.recipient_email == admin.email)
            .order_by(AdminNotification.created_at.desc())
            .limit(100)
        ).all()
        return [
            AdminNotice(
                id=item.id,
                applicant_email=item.applicant_email,
                event=item.event,
                created_at=item.created_at,
                read=item.read_at is not None,
            )
            for item in notifications
        ]


def _assign_role(context, user_id, role):
    with _session(context) as session:
        actor = _admin(context, session)
        target = session.get(User, str(user_id))
        if target is None:
            raise GraphQLError("User not found")
        if target.role == "superadmin" or target.id == actor.id:
            raise GraphQLError("This account role cannot be changed here")
        if role == UserRole.SUPERADMIN:
            raise GraphQLError(
                "Superadmin is reserved for the configured owner account"
            )
        if actor.role == "admin" and role not in {UserRole.VIEWER, UserRole.EDITOR}:
            raise GraphQLError("Admins can assign viewer or editor roles")
        if not target.email_verified:
            raise GraphQLError("Verify the user's email before assigning a role")
        target.role = role.value
        target.status = "active"
        session.commit()
        return _admin_user(target)


def _create_user(context, name, email, persona):
    _limit_auth(context)
    name = name.strip()
    if not 1 <= len(name) <= 80:
        raise GraphQLError("Name must be 1 to 80 characters")
    normalized_email = _normalize_email(email)
    with _session(context) as session:
        _superadmin(context, session)
        if session.scalar(select(User.id).where(User.email == normalized_email)):
            raise GraphQLError("Email already registered")
        user = User(
            name=name,
            email=normalized_email,
            persona=_persona(persona),
            role="viewer",
            status="email_pending",
            email_verified=False,
        )
        session.add(user)
        session.flush()
        return _send_verification(context, session, user)


def _remove_user(context, user_id):
    with _session(context) as session:
        actor = _superadmin(context, session)
        target = session.get(User, str(user_id))
        if target is None:
            return False
        if target.id == actor.id or target.role == "superadmin":
            raise GraphQLError("The owner account cannot be removed")
        session.delete(target)
        session.commit()
        return True


def _mark_notification_read(context, notification_id):
    with _session(context) as session:
        admin = _admin(context, session)
        notification = session.scalar(
            select(AdminNotification).where(
                AdminNotification.id == str(notification_id),
                AdminNotification.recipient_email == admin.email,
            )
        )
        if notification is None:
            return False
        notification.read_at = context["clock"]()
        session.commit()
        return True


def _logout(context):
    now = context["clock"]()
    with _session(context) as session:
        token = context["request"].cookies.get(ACCESS_COOKIE)
        claims = (
            read_token(token, context["settings"].jwt_secret, now, "access")
            if token
            else None
        )
        if claims:
            auth_session = session.get(AuthSession, claims["sid"])
            if auth_session is not None and auth_session.revoked_at is None:
                auth_session.revoked_at = now
        revoke_refresh_session(context["request"], session, context["settings"], now)
        session.commit()
    clear_auth_cookies(context["response"])
    return True


def _add_transaction(context, data):
    merchant = data.merchant.strip()
    if not 2 <= len(merchant) <= 100:
        raise GraphQLError("Merchant must be 2 to 100 characters")
    if not 0 < data.amount_minor <= 100_000_000_000:
        raise GraphQLError("Amount must be greater than zero")
    if data.occurred_at.tzinfo is None or data.occurred_at > context[
        "clock"
    ]() + timedelta(minutes=5):
        raise GraphQLError("Enter a valid transaction date")
    if (
        data.city
        and len(data.city.strip()) > 80
        or data.note
        and len(data.note.strip()) > 240
    ):
        raise GraphQLError("City or note is too long")
    with _session(context) as session:
        user = _writer(context, session)
        transaction = Transaction(
            user_id=user.id,
            merchant=merchant,
            amount_minor=data.amount_minor,
            category=(data.category or Category(categorize_merchant(merchant))).value,
            method=data.method.value,
            occurred_at=data.occurred_at.astimezone(UTC),
            city=data.city.strip() if data.city else None,
            note=data.note.strip() if data.note else None,
        )
        session.add(transaction)
        session.commit()
        return _transaction(transaction)


def _set_budget(context, data):
    _month_start(data.month)
    if not 0 < data.limit_minor <= 100_000_000_000:
        raise GraphQLError("Budget must be greater than zero")
    with _session(context) as session:
        user = _writer(context, session)
        budget = session.scalar(
            select(Budget).where(
                Budget.user_id == user.id,
                Budget.month == data.month,
                Budget.category == data.category.value,
            )
        )
        if budget:
            budget.limit_minor = data.limit_minor
        else:
            budget = Budget(
                user_id=user.id,
                month=data.month,
                category=data.category.value,
                limit_minor=data.limit_minor,
            )
            session.add(budget)
        session.commit()
        return _budget_node(session, user.id, budget)


def _import_csv(context, csv_text):
    with _session(context) as session:
        user = _writer(context, session)
        try:
            rows = parse_transactions(csv_text, now=context["clock"]())
        except ValueError as error:
            raise GraphQLError(str(error)) from error
        session.add_all(
            Transaction(user_id=user.id, source="csv", **row) for row in rows
        )
        session.commit()
        return ImportResult(imported=len(rows))


def _export_csv(context):
    with _session(context) as session:
        user = _user(context, session)
        transactions = session.scalars(
            select(Transaction)
            .where(Transaction.user_id == user.id)
            .order_by(Transaction.occurred_at.desc())
            .limit(5001)
        ).all()
        if len(transactions) > 5000:
            raise GraphQLError("Export supports up to 5000 transactions")
        return export_transactions(transactions)


def _update_category(context, transaction_id, category):
    with _session(context) as session:
        user = _writer(context, session)
        transaction = session.scalar(
            select(Transaction).where(
                Transaction.id == str(transaction_id), Transaction.user_id == user.id
            )
        )
        if transaction is None:
            raise GraphQLError("Transaction not found")
        transaction.category = category.value
        session.commit()
        return _transaction(transaction)


def _delete_transaction(context, transaction_id):
    with _session(context) as session:
        user = _writer(context, session)
        transaction = session.scalar(
            select(Transaction).where(
                Transaction.id == str(transaction_id), Transaction.user_id == user.id
            )
        )
        if transaction is None:
            return False
        session.delete(transaction)
        session.commit()
        return True


@strawberry.type
class Query:
    @strawberry.field
    async def viewer(self, info: Info) -> Viewer:
        def load():
            with _session(info.context) as session:
                return _viewer(_user(info.context, session))

        return await run_in_threadpool(load)

    @strawberry.field
    async def overview(self, info: Info) -> Overview:
        return await run_in_threadpool(_overview, info.context)

    @strawberry.field
    async def transactions(
        self,
        info: Info,
        limit: int = 25,
        offset: int = 0,
        filter: TransactionFilter | None = None,
    ) -> TransactionPage:
        return await run_in_threadpool(
            _transactions, info.context, limit, offset, filter
        )

    @strawberry.field
    async def budgets(self, info: Info, month: str | None = None) -> list[BudgetNode]:
        return await run_in_threadpool(_budgets, info.context, month)

    @strawberry.field
    async def export_csv(self, info: Info) -> str:
        return await run_in_threadpool(_export_csv, info.context)

    @strawberry.field
    async def pending_users(self, info: Info) -> list[AdminUser]:
        return await run_in_threadpool(_pending_users, info.context)

    @strawberry.field
    async def managed_users(self, info: Info) -> list[AdminUser]:
        return await run_in_threadpool(_managed_users, info.context)

    @strawberry.field
    async def admin_notifications(self, info: Info) -> list[AdminNotice]:
        return await run_in_threadpool(_admin_notifications, info.context)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def demo_session(self, info: Info) -> Viewer:
        return await run_in_threadpool(_demo_session, info.context)

    @strawberry.mutation
    async def register(
        self,
        info: Info,
        name: str,
        email: str,
        password: str,
        persona: str = "Personal",
    ) -> AuthOutcome:
        return await run_in_threadpool(
            _register, info.context, name, email, password, persona
        )

    @strawberry.mutation
    async def login(
        self, info: Info, email: str, password: str, persona: str = "Personal"
    ) -> AuthOutcome:
        return await run_in_threadpool(_login, info.context, email, password, persona)

    @strawberry.mutation
    async def verify_email(self, info: Info, email: str, code: str) -> Viewer:
        return await run_in_threadpool(_verify_email, info.context, email, code)

    @strawberry.mutation
    async def resend_verification_code(self, info: Info, email: str) -> bool:
        return await run_in_threadpool(_resend_verification, info.context, email)

    @strawberry.mutation
    async def update_profile(self, info: Info, name: str, persona: str) -> Viewer:
        return await run_in_threadpool(_update_profile, info.context, name, persona)

    @strawberry.mutation
    async def logout(self, info: Info) -> bool:
        return await run_in_threadpool(_logout, info.context)

    @strawberry.mutation
    async def assign_role(
        self, info: Info, user_id: strawberry.ID, role: UserRole
    ) -> AdminUser:
        return await run_in_threadpool(_assign_role, info.context, user_id, role)

    @strawberry.mutation
    async def create_user(
        self, info: Info, name: str, email: str, persona: str = "Work"
    ) -> AuthOutcome:
        return await run_in_threadpool(_create_user, info.context, name, email, persona)

    @strawberry.mutation
    async def remove_user(self, info: Info, user_id: strawberry.ID) -> bool:
        return await run_in_threadpool(_remove_user, info.context, user_id)

    @strawberry.mutation
    async def mark_admin_notification_read(self, info: Info, id: strawberry.ID) -> bool:
        return await run_in_threadpool(_mark_notification_read, info.context, id)

    @strawberry.mutation
    async def add_transaction(
        self, info: Info, input: TransactionInput
    ) -> TransactionNode:
        return await run_in_threadpool(_add_transaction, info.context, input)

    @strawberry.mutation
    async def set_budget(self, info: Info, input: BudgetInput) -> BudgetNode:
        return await run_in_threadpool(_set_budget, info.context, input)

    @strawberry.mutation
    async def import_csv(self, info: Info, csv_text: str) -> ImportResult:
        return await run_in_threadpool(_import_csv, info.context, csv_text)

    @strawberry.mutation
    async def update_transaction_category(
        self, info: Info, id: strawberry.ID, category: Category
    ) -> TransactionNode:
        return await run_in_threadpool(_update_category, info.context, id, category)

    @strawberry.mutation
    async def delete_transaction(self, info: Info, id: strawberry.ID) -> bool:
        return await run_in_threadpool(_delete_transaction, info.context, id)


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[
        lambda: MaxTokensLimiter(max_token_count=2000),
        lambda: QueryDepthLimiter(max_depth=8),
    ],
)
