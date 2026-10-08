from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base, make_engine
from app.models import Transaction, User


def test_sqlite_demo_database_enforces_workspace_cascades():
    engine = make_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(name="Asha", email="asha@example.com")
        session.add(user)
        session.flush()
        session.add(
            Transaction(
                user_id=user.id,
                merchant="Cafe",
                amount_minor=100,
                category="Food",
                method="upi",
                occurred_at=datetime.now(UTC),
                source="manual",
            )
        )
        session.commit()
        session.delete(user)
        session.commit()
        assert session.scalar(select(func.count(Transaction.id))) == 0
    engine.dispose()
