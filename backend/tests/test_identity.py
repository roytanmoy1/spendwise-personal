import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base
from app.email import EmailDeliveryUnavailable
from app.main import create_app
from app.models import (
    AdminNotification,
    AuthSession,
    EmailVerification,
    RefreshToken,
    User,
)
from app.security import password_hash

TEST_SECRET = "identity-test-signing-secret-with-enough-entropy"
NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


class FakeMailer:
    def __init__(self):
        self.messages = []

    def __call__(self, recipient, subject, body):
        self.messages.append({"recipient": recipient, "subject": subject, "body": body})

    def code_for(self, recipient):
        message = next(
            item for item in reversed(self.messages) if item["recipient"] == recipient
        )
        return re.search(r"\b(\d{6})\b", message["body"]).group(1)


def make_identity_client(
    *,
    superadmin_email="owner@example.com",
    clock=None,
    email_sender=None,
    **settings_overrides,
):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    mailer = FakeMailer()
    settings = Settings(
        database_url="sqlite+pysqlite://",
        jwt_secret=TEST_SECRET,
        demo_mode=True,
        superadmin_email=superadmin_email,
        **settings_overrides,
    )
    app = create_app(
        settings=settings,
        engine=engine,
        clock=clock or (lambda: NOW),
        email_sender=email_sender or mailer,
    )
    return TestClient(app), engine, mailer


def gql(client, query, variables=None):
    response = client.post(
        "/graphql", json={"query": query, "variables": variables or {}}
    )
    assert response.status_code == 200
    return response.json()


def register_account(
    client,
    email,
    *,
    name="Test User",
    password="a-long-passphrase-for-testing",
    persona="Personal",
):
    return gql(
        client,
        """mutation Register($name: String!, $email: String!, $password: String!, $persona: String!) {
          register(name: $name, email: $email, password: $password, persona: $persona) {
            authenticated requiresVerification message
          }
        }""",
        {"name": name, "email": email, "password": password, "persona": persona},
    )


def test_login_unknown_email_requests_registration_without_creating_account():
    client, engine, mailer = make_identity_client()
    with client:
        result = gql(
            client,
            """mutation {
              login(email: "new@example.com", password: "a-long-passphrase-for-testing") {
                authenticated requiresVerification requiresRegistration
              }
            }""",
        )
        assert "errors" not in result, result
        outcome = result["data"]["login"]
        assert outcome["authenticated"] is False
        assert outcome["requiresVerification"] is False
        assert outcome["requiresRegistration"] is True
        assert mailer.messages == []
        with engine.begin() as connection:
            assert (
                connection.execute(
                    select(User).where(User.email == "new@example.com")
                ).scalar_one_or_none()
                is None
            )
            assert connection.execute(select(EmailVerification)).scalar_one_or_none() is None


def test_registration_creates_verified_read_only_account_and_notifies_admin():
    client, engine, mailer = make_identity_client()
    with client:
        created = gql(
            client,
            """mutation {
                    register(name: "Analyst", email: "analyst@example.com", password: "a-long-passphrase-for-testing", persona: "Research") {
            authenticated requiresVerification message
          }
        }""",
        )
        assert "errors" not in created, created
        outcome = created["data"]["register"]
        assert outcome["authenticated"] is False
        assert outcome["requiresVerification"] is True
        assert mailer.messages[-1]["recipient"] == "analyst@example.com"
        assert mailer.code_for("analyst@example.com") not in outcome["message"]

        with engine.begin() as connection:
            user = connection.execute(
                select(User).where(User.email == "analyst@example.com")
            ).one()
            challenge = connection.execute(select(EmailVerification)).one()
            assert user.email_verified is False
            assert user.status == "email_pending"
            assert user.role == "viewer"
            assert challenge.code_hash != mailer.code_for("analyst@example.com")

        verified = gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { id email role status persona emailVerified }
        }""",
            {
                "email": "analyst@example.com",
                "code": mailer.code_for("analyst@example.com"),
            },
        )
        assert "errors" not in verified, verified
        profile = verified["data"]["verifyEmail"]
        assert profile["role"] == "VIEWER"
        assert profile["status"] == "PENDING_REVIEW"
        assert profile["persona"] == "Research"
        assert profile["emailVerified"] is True
        assert "spendwise_access" in client.cookies
        assert "spendwise_refresh" in client.cookies

        read_only = gql(client, "{ viewer { email role status persona } }")
        assert read_only["data"]["viewer"]["email"] == "analyst@example.com"
        write = gql(
            client,
            """mutation {
          addTransaction(input: { merchant: "Cafe", amountMinor: 100, method: UPI, occurredAt: "2026-10-04T10:00:00Z" }) { id }
        }""",
        )
        assert (
            write["errors"][0]["message"] == "Your account is awaiting access approval"
        )

        with engine.begin() as connection:
            notification = connection.execute(select(AdminNotification)).one()
            assert notification.recipient_email == "owner@example.com"
            assert notification.applicant_user_id == profile["id"]
        assert any(
            message["recipient"] == "owner@example.com" for message in mailer.messages
        )


def test_login_rejects_short_password_for_existing_account():
    client, engine, _ = make_identity_client()
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert().values(
                id="known-user",
                name="Known User",
                email="known@example.com",
                password_hash=password_hash.hash("a-long-passphrase-for-testing"),
                persona="Personal",
                role="editor",
                status="active",
                email_verified=True,
                created_at=NOW,
            )
        )

    with client:
        result = gql(
            client,
            """mutation {
              login(email: "known@example.com", password: "short") { authenticated }
            }""",
        )
        assert result["errors"][0]["message"] == "Invalid credentials"


def test_superadmin_is_bootstrapped_only_after_email_otp_verification():
    client, engine, mailer = make_identity_client(superadmin_email="owner@example.com")
    with client:
        created = register_account(client, "OWNER@example.com", name="Owner")
        assert created["data"]["register"]["requiresVerification"] is True
        with engine.begin() as connection:
            owner = connection.execute(
                select(User).where(User.email == "owner@example.com")
            ).one()
            assert owner.role == "viewer"

        verified = gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { role status }
        }""",
            {
                "email": "owner@example.com",
                "code": mailer.code_for("owner@example.com"),
            },
        )
        assert "errors" not in verified, verified
        assert verified["data"]["verifyEmail"] == {
            "role": "SUPERADMIN",
            "status": "ACTIVE",
        }
        with engine.begin() as connection:
            assert connection.execute(select(AdminNotification)).all() == []


def test_refresh_rotates_tokens_and_reuse_revokes_the_session():
    client, engine, mailer = make_identity_client()
    with client:
        register_account(client, "owner@example.com", name="Owner")
        code = mailer.code_for("owner@example.com")
        gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { role }
        }""",
            {"email": "owner@example.com", "code": code},
        )
        old_refresh = client.cookies.get("spendwise_refresh")
        old_access = client.cookies.get("spendwise_access")
        first_session_id = gql(client, "{ viewer { id } }")["data"]["viewer"]["id"]

        origin = {"Origin": "http://127.0.0.1:5173"}
        refreshed = client.post("/auth/refresh", headers=origin)
        assert refreshed.status_code == 204
        rotated_refresh = client.cookies.get("spendwise_refresh")
        assert rotated_refresh != old_refresh
        assert client.cookies.get("spendwise_access") != old_access
        assert (
            gql(client, "{ viewer { id } }")["data"]["viewer"]["id"] == first_session_id
        )

        reuse = client.post(
            "/auth/refresh",
            headers={**origin, "Cookie": f"spendwise_refresh={old_refresh}"},
        )
        assert reuse.status_code == 401
        assert "errors" in gql(client, "{ viewer { id } }")
        with engine.begin() as connection:
            session = connection.execute(select(AuthSession)).one()
            assert session.revoked_at is not None
            tokens = connection.execute(select(RefreshToken)).all()
            assert all(
                token.token_hash not in {old_refresh, rotated_refresh}
                for token in tokens
            )


def test_pending_users_are_isolated_and_role_changes_are_superadmin_only():
    owner_client, engine, mailer = make_identity_client()
    applicant_client = TestClient(owner_client.app)
    with owner_client, applicant_client:
        created = register_account(owner_client, "owner@example.com", name="Owner")
        assert created["data"]["register"]["requiresVerification"]
        owner = gql(
            owner_client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { id role }
        }""",
            {
                "email": "owner@example.com",
                "code": mailer.code_for("owner@example.com"),
            },
        )
        owner_id = owner["data"]["verifyEmail"]["id"]

        directory = gql(owner_client, "{ managedUsers { id email role status } }")
        assert "errors" not in directory, directory
        assert directory["data"]["managedUsers"] == []

        register_account(
            applicant_client,
            "new.person@example.com",
            name="New Person",
            persona="Client A",
        )
        gql(
            applicant_client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { id }
        }""",
            {
                "email": "new.person@example.com",
                "code": mailer.code_for("new.person@example.com"),
            },
        )

        pending = gql(owner_client, "{ pendingUsers { id email role status persona } }")
        assert "errors" not in pending, pending
        applicant = next(
            item
            for item in pending["data"]["pendingUsers"]
            if item["email"] == "new.person@example.com"
        )
        assigned = gql(
            owner_client,
            """mutation Role($id: ID!, $role: UserRole!) {
          assignRole(userId: $id, role: $role) { id role status }
        }""",
            {"id": applicant["id"], "role": "EDITOR"},
        )
        assert assigned["data"]["assignRole"]["status"] == "ACTIVE"
        writable = gql(
            applicant_client,
            """mutation {
          addTransaction(input: { merchant: "Work lunch", amountMinor: 1234, method: CARD, occurredAt: "2026-10-04T10:00:00Z" }) { id }
        }""",
        )
        assert "errors" not in writable, writable

        removed = gql(
            owner_client,
            "mutation Remove($id: ID!) { removeUser(userId: $id) }",
            {"id": applicant["id"]},
        )
        assert removed["data"]["removeUser"] is True
        with engine.begin() as connection:
            assert (
                connection.execute(
                    select(User).where(User.id == applicant["id"])
                ).scalar_one_or_none()
                is None
            )
            assert (
                connection.execute(
                    select(User.role).where(User.id == owner_id)
                ).scalar_one()
                == "superadmin"
            )


def test_google_oauth_is_disabled_until_credentials_are_configured():
    client, _, _ = make_identity_client()
    with client:
        response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert response.headers["location"].endswith("/login?error=google_not_configured")


def test_google_callback_creates_account_and_requires_email_otp():
    client, _, mailer = make_identity_client(
        google_client_id="test-client-id",
        google_client_secret="test-client-secret",
    )
    client.app.state.google_oauth.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-subject-1",
                "email": "google.person@example.com",
                "email_verified": True,
                "name": "Google Person",
            }
        }
    )
    client.app.state.google_oauth.authorize_redirect = AsyncMock(
        return_value=RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth")
    )
    with client:
        start = client.get("/auth/google", follow_redirects=False)
        assert start.status_code in {302, 307}
        assert start.headers["location"].startswith("https://accounts.google.com/")
        response = client.get("/auth/google/callback", follow_redirects=False)
        assert response.status_code in {302, 307}
        assert response.headers["location"].endswith(
            "/verify-email?email=google.person%40example.com"
        )
        assert mailer.code_for("google.person@example.com")
        gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
              verifyEmail(email: $email, code: $code) { email }
            }""",
            {
                "email": "google.person@example.com",
                "code": mailer.code_for("google.person@example.com"),
            },
        )
        signed_in = client.get("/auth/google/callback", follow_redirects=False)
        assert signed_in.headers["location"] == "http://127.0.0.1:5173/"
        assert "spendwise_access" in signed_in.headers["set-cookie"]
        assert "spendwise_refresh" in signed_in.headers["set-cookie"]


def test_profile_updates_persona_without_changing_login_email():
    client, _, mailer = make_identity_client()
    with client:
        register_account(client, "owner@example.com", name="Owner")
        gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
            verifyEmail(email: $email, code: $code) { id }
          }""",
            {
                "email": "owner@example.com",
                "code": mailer.code_for("owner@example.com"),
            },
        )
        updated = gql(
            client,
            """mutation { updateProfile(name: "Tanmoy", persona: "Consulting") {
            name email persona role
          } }""",
        )
        assert "errors" not in updated, updated
        assert updated["data"]["updateProfile"] == {
            "name": "Tanmoy",
            "email": "owner@example.com",
            "persona": "Consulting",
            "role": "SUPERADMIN",
        }


def test_auth_endpoints_reject_cross_origin_and_oversized_cookie_posts():
    client, _, _ = make_identity_client()
    with client:
        cross_origin = client.post(
            "/auth/logout",
            headers={"Origin": "https://untrusted.invalid"},
            content="{}",
        )
        assert cross_origin.status_code == 403
        missing_origin = client.post("/auth/logout", content="{}")
        assert missing_origin.status_code == 403
        oversized = client.post(
            "/auth/logout",
            headers={"Origin": "http://127.0.0.1:5173", "Content-Length": "9000"},
            content="{}",
        )
        assert oversized.status_code == 413


def test_email_otp_expires_and_is_invalidated_after_five_wrong_attempts():
    instant = [NOW]
    client, _, mailer = make_identity_client(
        clock=lambda: instant[0], otp_attempts_per_minute=10
    )
    with client:
        register_account(client, "expired@example.com")
        valid_code = mailer.code_for("expired@example.com")
        wrong_code = f"{(int(valid_code) + 1) % 1_000_000:06d}"
        for _ in range(5):
            result = gql(
                client,
                """mutation Verify($email: String!, $code: String!) {
              verifyEmail(email: $email, code: $code) { id }
            }""",
                {"email": "expired@example.com", "code": wrong_code},
            )
            assert (
                result["errors"][0]["message"] == "Invalid or expired verification code"
            )
        exhausted = gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { id }
        }""",
            {"email": "expired@example.com", "code": valid_code},
        )
        assert (
            exhausted["errors"][0]["message"] == "Invalid or expired verification code"
        )

        register_account(client, "late@example.com")
        late_code = mailer.code_for("late@example.com")
        instant[0] = NOW + timedelta(minutes=11)
        expired = gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { id }
        }""",
            {"email": "late@example.com", "code": late_code},
        )
        assert expired["errors"][0]["message"] == "Invalid or expired verification code"


def test_login_routes_unknown_email_to_registration_and_wrong_password_to_recovery():
    client, _, mailer = make_identity_client(
        auth_attempts_per_minute=20, otp_attempts_per_minute=20
    )
    with client:
        unknown = gql(
            client,
            """mutation {
          login(email: "new@example.com", password: "a-long-passphrase-for-testing") {
            authenticated requiresVerification requiresRegistration
          }
        }""",
        )["data"]["login"]
        assert unknown["authenticated"] is False
        assert unknown["requiresVerification"] is False
        assert unknown["requiresRegistration"] is True
        assert mailer.messages == []

        register_account(client, "new@example.com", name="New User")
        gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
          verifyEmail(email: $email, code: $code) { id }
        }""",
            {"email": "new@example.com", "code": mailer.code_for("new@example.com")},
        )
        wrong_password = gql(
            client,
            """mutation {
          login(email: "new@example.com", password: "another-long-passphrase") {
                        authenticated requiresVerification requiresPasswordSetup
          }
        }""",
        )["data"]["login"]
        assert wrong_password["authenticated"] is False
        assert wrong_password["requiresVerification"] is True
        assert wrong_password["requiresPasswordSetup"] is True


def test_invited_user_sets_password_after_email_proof():
    owner_client, _, mailer = make_identity_client()
    invited_client = TestClient(owner_client.app)
    with owner_client, invited_client:
        register_account(owner_client, "owner@example.com", name="Owner")
        gql(
            owner_client,
            """mutation Verify($email: String!, $code: String!) {
                            verifyEmail(email: $email, code: $code) { role }
                        }""",
            {
                "email": "owner@example.com",
                "code": mailer.code_for("owner@example.com"),
            },
        )
        invite = gql(
            owner_client,
            """mutation {
                            createUser(name: "Mina", email: "mina@example.com", persona: "Client B") {
                                requiresVerification
                            }
                        }""",
        )
        assert invite["data"]["createUser"]["requiresVerification"] is True
        started = gql(
            invited_client,
            """mutation {
                            login(email: "mina@example.com", password: "a-new-long-password") {
                                requiresVerification
                            }
                        }""",
        )
        assert started["data"]["login"]["requiresVerification"] is True
        gql(
            invited_client,
            """mutation Verify($email: String!, $code: String!) {
                            verifyEmail(email: $email, code: $code) { status persona }
                        }""",
            {"email": "mina@example.com", "code": mailer.code_for("mina@example.com")},
        )
        signed_in = gql(
            invited_client,
            """mutation {
                            login(email: "mina@example.com", password: "a-new-long-password") {
                                authenticated viewer { email status persona }
                            }
                        }""",
        )
        assert signed_in["data"]["login"]["authenticated"] is True
        assert signed_in["data"]["login"]["viewer"]["status"] == "PENDING_REVIEW"


def test_legacy_password_hash_is_replaced_only_after_email_otp():
    client, engine, mailer = make_identity_client()
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert().values(
                id="legacy-user",
                name="Legacy User",
                email="legacy@example.com",
                password_hash="old-client-hash-format",
                persona="Personal",
                role="editor",
                status="active",
                email_verified=True,
                created_at=NOW,
            )
        )

    with client:
        outcome = gql(
            client,
            """mutation {
              login(email: "legacy@example.com", password: "new-long-password-for-account") {
                                authenticated requiresVerification requiresPasswordSetup
              }
            }""",
        )
        assert "errors" not in outcome, outcome
        assert outcome["data"]["login"]["requiresVerification"] is True
        assert outcome["data"]["login"]["requiresPasswordSetup"] is True
        original_code = mailer.code_for("legacy@example.com")
        with engine.begin() as connection:
            stored_before_verify = connection.execute(
                select(User.password_hash).where(User.email == "legacy@example.com")
            ).scalar_one()
            reset_hash_before_resend = connection.execute(
                select(EmailVerification.password_reset_hash)
            ).scalar_one()
            assert stored_before_verify == "old-client-hash-format"
            assert reset_hash_before_resend

        gql(
            client,
            """mutation { resendVerificationCode(email: "legacy@example.com") }""",
        )
        with engine.begin() as connection:
            reset_hash_after_resend = connection.execute(
                select(EmailVerification.password_reset_hash)
            ).scalar_one()
        assert reset_hash_after_resend == reset_hash_before_resend
        assert mailer.code_for("legacy@example.com") != original_code

        verified = gql(
            client,
            """mutation Verify($email: String!, $code: String!) {
              verifyEmail(email: $email, code: $code) { email role }
            }""",
            {
                "email": "legacy@example.com",
                "code": mailer.code_for("legacy@example.com"),
            },
        )
        assert "errors" not in verified, verified
        with engine.begin() as connection:
            stored_after_verify = connection.execute(
                select(User.password_hash).where(User.email == "legacy@example.com")
            ).scalar_one()
            assert stored_after_verify != "old-client-hash-format"

        login = gql(
            client,
            """mutation {
              login(email: "legacy@example.com", password: "new-long-password-for-account") {
                authenticated
              }
            }""",
        )
        assert login["data"]["login"]["authenticated"] is True


def test_resend_replaces_the_previous_code_and_delivery_failure_cleans_it_up():
    client, engine, mailer = make_identity_client()
    with client:
        register_account(client, "replace@example.com")
        first_code = mailer.code_for("replace@example.com")
        gql(
            client,
            """mutation { resendVerificationCode(email: "replace@example.com") }""",
        )
        second_code = mailer.code_for("replace@example.com")
        with engine.begin() as connection:
            challenge_hash, user_id = connection.execute(
                select(EmailVerification.code_hash, EmailVerification.user_id)
            ).one()
            from app.security import otp_hash

            assert challenge_hash == otp_hash(second_code, TEST_SECRET, user_id)
            assert challenge_hash != otp_hash(first_code, TEST_SECRET, user_id)

    def fail_delivery(recipient, subject, body):
        raise EmailDeliveryUnavailable("provider unavailable")

    failed_client, failed_engine, _ = make_identity_client(
        email_sender=fail_delivery,
        resend_api_key="test-resend-key",
        email_from="SpendWise <verify@example.com>",
    )
    with failed_client:
        result = register_account(failed_client, "delivery@example.com")
        assert (
            result["errors"][0]["message"]
            == "Email verification is temporarily unavailable. Try again later."
        )
        with failed_engine.begin() as connection:
            assert (
                connection.execute(select(EmailVerification)).scalar_one_or_none()
                is None
            )


def test_unconfigured_local_email_delivery_explains_demo_fallback():
    def fail_unconfigured_delivery(recipient, subject, body):
        raise EmailDeliveryUnavailable("Email delivery is not configured")

    client, engine, _ = make_identity_client(email_sender=fail_unconfigured_delivery)
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert().values(
                id="local-email-user",
                name="Local User",
                email="local@example.com",
                password_hash=password_hash.hash("a-long-passphrase-for-testing"),
                persona="Personal",
                role="viewer",
                status="email_pending",
                email_verified=False,
                created_at=NOW,
            )
        )
    with client:
        result = gql(
            client,
            """mutation {
              login(email: "local@example.com", password: "a-long-passphrase-for-testing") {
                authenticated requiresVerification message
              }
            }""",
        )
        assert result["errors"][0]["message"] == (
            "Email sign-in isn't configured. Configure Resend in the backend "
            "environment to enable email verification."
        )
        with engine.begin() as connection:
            assert (
                connection.execute(select(EmailVerification)).scalar_one_or_none()
                is None
            )
