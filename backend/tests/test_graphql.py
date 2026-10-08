import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base
from app.main import create_app

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)
TEST_SECRET = "test-only-session-secret-longer-than-32-bytes"


def make_client(**settings_overrides):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    email_sender = settings_overrides.pop("email_sender", None)
    settings = Settings(
        database_url="sqlite+pysqlite://",
        demo_mode=True,
        jwt_secret=TEST_SECRET,
        **settings_overrides,
    )
    return TestClient(
        create_app(
            settings=settings,
            engine=engine,
            clock=lambda: NOW,
            rate_clock=lambda: 100.0,
            email_sender=email_sender,
        )
    )


def graphql(client, query, variables=None):
    response = client.post(
        "/graphql", json={"query": query, "variables": variables or {}}
    )
    assert response.status_code == 200
    return response.json()


def test_demo_dashboard_mutations_and_validation():
    with make_client() as client:
        session_response = client.post(
            "/graphql", json={"query": "mutation { demoSession { id name } }"}
        )
        assert "httponly" in session_response.headers["set-cookie"].lower()
        session = session_response.json()
        assert "errors" not in session, session
        assert session["data"]["demoSession"]["name"] == "Demo account"
        assert "spendwise_access" in client.cookies

        overview_query = "{ overview { totalSpentMinor thisMonthMinor byCategory { category amountMinor } byCity { city amountMinor } } }"
        initial = graphql(client, overview_query)
        assert "errors" not in initial, initial
        amount_before = initial["data"]["overview"]["thisMonthMinor"]
        assert any(
            place["city"] == "Bengaluru"
            for place in initial["data"]["overview"]["byCity"]
        )

        add = graphql(
            client,
            """mutation {
              addTransaction(input: {
                merchant: "Apollo Pharmacy", amountMinor: 4500, method: UPI,
                occurredAt: "2026-10-03T08:00:00Z", city: "Bengaluru"
              }) { id category amountMinor }
            }""",
        )
        assert "errors" not in add, add
        assert add["data"]["addTransaction"]["category"] == "HEALTH"

        overview = graphql(client, overview_query)
        assert overview["data"]["overview"]["thisMonthMinor"] == amount_before + 4500
        page = graphql(
            client,
            "{ transactions(limit: 1) { totalCount hasMore items { id merchant } } }",
        )
        assert page["data"]["transactions"]["totalCount"] > 1
        assert page["data"]["transactions"]["hasMore"] is True

        budget = graphql(
            client,
            """mutation {
              setBudget(input: { category: HEALTH, month: "2026-10", limitMinor: 10000 }) {
                category limitMinor spentMinor
              }
            }""",
        )
        assert "errors" not in budget, budget
        assert budget["data"]["setBudget"]["spentMinor"] >= 4500

        invalid = graphql(
            client,
            """mutation {
              addTransaction(input: {
                merchant: "Invalid", amountMinor: -1, method: UPI,
                occurredAt: "2026-10-03T08:00:00Z"
              }) { id }
            }""",
        )
        assert invalid["errors"][0]["message"] == "Amount must be greater than zero"


def test_demo_sessions_do_not_share_transactions():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app = create_app(
        settings=Settings(
            database_url="sqlite+pysqlite://", demo_mode=True, jwt_secret=TEST_SECRET
        ),
        engine=engine,
        clock=lambda: NOW,
    )
    with TestClient(app) as first, TestClient(app) as second:
        assert "errors" not in graphql(first, "mutation { demoSession { id } }")
        assert "errors" not in graphql(second, "mutation { demoSession { id } }")
        result = graphql(
            first,
            """mutation {
              addTransaction(input: {
                merchant: "Private purchase", amountMinor: 9900, method: CARD,
                occurredAt: "2026-10-03T08:00:00Z"
              }) { id }
            }""",
        )
        assert "errors" not in result, result
        second_page = graphql(
            second,
            """{
              transactions(filter: { merchant: "Private purchase" }) { totalCount }
            }""",
        )
        assert second_page["data"]["transactions"]["totalCount"] == 0


def test_private_queries_need_a_session():
    with make_client() as client:
        result = graphql(client, "{ overview { totalSpentMinor } }")
        assert result["errors"][0]["message"] == "Sign in to continue"


def test_graphql_and_auth_rate_limits():
    with make_client(graphql_requests_per_minute=2) as client:
        assert "errors" not in graphql(client, "{ __typename }")
        assert "errors" not in graphql(client, "{ __typename }")
        assert (
            client.post("/graphql", json={"query": "{ __typename }"}).status_code == 429
        )

    with make_client(auth_attempts_per_minute=1) as client:
        attempt = 'mutation { login(email: "nobody@example.com", password: "incorrect") { authenticated requiresRegistration } }'
        first_attempt = graphql(client, attempt)
        assert first_attempt["data"]["login"]["requiresRegistration"] is True
        assert (
            graphql(client, attempt)["errors"][0]["message"]
            == "Too many attempts. Try again later."
        )


def test_registration_rejects_short_password():
    with make_client() as client:
        short_registration = graphql(
            client,
            """mutation {
              register(name: "Asha", email: "short@example.com", password: "short", persona: "Personal") {
                authenticated
              }
            }""",
        )
        assert short_registration["errors"][0]["message"] == (
            "Enter a name and a password of at least 12 characters"
        )


def test_graphql_get_queries_share_the_request_limit():
    with make_client(graphql_requests_per_minute=1) as client:
        assert (
            client.get("/graphql", params={"query": "{ __typename }"}).status_code
            == 200
        )
        assert (
            client.get("/graphql", params={"query": "{ __typename }"}).status_code
            == 429
        )


def test_graphql_rejects_oversized_alias_query():
    with make_client() as client:
        aliases = " ".join(f"field{index}: __typename" for index in range(1100))
        response = client.post("/graphql", json={"query": "{ " + aliases + " }"})
        assert response.status_code in {200, 400}
        assert "errors" in response.json()


def test_csv_import_correction_export_and_delete():
    with make_client() as client:
        graphql(client, "mutation { demoSession { id } }")
        import_csv = (
            "merchant,amount,date,method,city\n"
            "=1+1,12.50,2026-10-02T10:00:00Z,card,Bengaluru\n"
            "Apollo Pharmacy,45.00,2026-10-03T10:00:00Z,upi,Mumbai\n"
        )
        imported = graphql(
            client,
            "mutation Import($csv: String!) { importCsv(csvText: $csv) { imported } }",
            {"csv": import_csv},
        )
        assert "errors" not in imported, imported
        assert imported["data"]["importCsv"]["imported"] == 2

        page = graphql(
            client,
            """{
              transactions(filter: { merchant: "Apollo Pharmacy" }) { items { id category } }
            }""",
        )
        transaction_id = page["data"]["transactions"]["items"][0]["id"]
        corrected = graphql(
            client,
            "mutation Correct($id: ID!) { updateTransactionCategory(id: $id, category: SHOPPING) { category } }",
            {"id": transaction_id},
        )
        assert corrected["data"]["updateTransactionCategory"]["category"] == "SHOPPING"

        exported = graphql(client, "{ exportCsv }")
        assert "'=1+1" in exported["data"]["exportCsv"]
        assert "Apollo Pharmacy" in exported["data"]["exportCsv"]

        deleted = graphql(
            client,
            "mutation Delete($id: ID!) { deleteTransaction(id: $id) }",
            {"id": transaction_id},
        )
        assert deleted["data"]["deleteTransaction"] is True
        after = graphql(
            client,
            '{ transactions(filter: { merchant: "Apollo Pharmacy" }) { totalCount } }',
        )
        assert after["data"]["transactions"]["totalCount"] == 3


def test_bad_csv_rejects_every_row_without_partial_writes():
    with make_client() as client:
        graphql(client, "mutation { demoSession { id } }")
        count_before = graphql(client, "{ transactions { totalCount } }")["data"][
            "transactions"
        ]["totalCount"]
        result = graphql(
            client,
            "mutation Import($csv: String!) { importCsv(csvText: $csv) { imported } }",
            {
                "csv": (
                    "merchant,amount,date,method\n"
                    "Cafe Mellow,10.50,2026-10-02T10:00:00Z,upi\n"
                    "Bad Entry,0.001,2026-10-03T10:00:00Z,card\n"
                )
            },
        )
        assert result["errors"][0]["message"] == "Row 3 has an invalid amount"
        count_after = graphql(client, "{ transactions { totalCount } }")["data"][
            "transactions"
        ]["totalCount"]
        assert count_after == count_before


def test_register_login_logout_and_origin_protection():
    sent_emails = []
    with make_client(
        email_sender=lambda *message: sent_emails.append(message)
    ) as client:
        blocked = client.post(
            "/graphql",
            headers={"Origin": "https://untrusted.invalid"},
            json={"query": "mutation { demoSession { id } }"},
        )
        assert blocked.status_code == 403
        allowed = client.post(
            "/graphql",
            headers={"Origin": "http://127.0.0.1:5173"},
            json={"query": "{ __typename }"},
        )
        assert allowed.status_code == 200

        registered = graphql(
            client,
            """mutation {
              register(name: "Asha", email: "ASHA@example.com", password: "long-test-password") {
                authenticated requiresVerification
              }
            }""",
        )
        assert registered["data"]["register"]["requiresVerification"] is True
        otp = re.search(r"\b(\d{6})\b", sent_emails[-1][2]).group(1)
        verified = graphql(
            client,
            """mutation Verify($email: String!, $code: String!) {
              verifyEmail(email: $email, code: $code) { name status }
            }""",
            {"email": "asha@example.com", "code": otp},
        )
        assert verified["data"]["verifyEmail"]["status"] == "PENDING_REVIEW"
        assert (
            graphql(client, "{ viewer { name } }")["data"]["viewer"]["name"] == "Asha"
        )

        graphql(client, "mutation { logout }")
        assert "errors" in graphql(client, "{ viewer { id } }")
        login = graphql(
            client,
            """mutation {
              login(email: "asha@example.com", password: "long-test-password") {
                authenticated viewer { name role status }
              }
            }""",
        )
        assert login["data"]["login"]["authenticated"] is True
        assert login["data"]["login"]["viewer"]["role"] == "VIEWER"
