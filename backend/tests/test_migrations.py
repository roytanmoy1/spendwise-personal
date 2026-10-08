from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from app.db import Base, make_engine
from app.models import (
    AdminNotification,
    AuthSession,
    Budget,
    EmailVerification,
    RefreshToken,
    Transaction,
    User,
)


def test_initial_migration_matches_models_and_can_downgrade(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.chdir(tmp_path)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    command.upgrade(config, "head")
    engine = make_engine(database_url)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert {
            User.__tablename__,
            Transaction.__tablename__,
            Budget.__tablename__,
            EmailVerification.__tablename__,
            AuthSession.__tablename__,
            RefreshToken.__tablename__,
            AdminNotification.__tablename__,
        } <= tables
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
    engine.dispose()

    command.downgrade(config, "base")
    engine = make_engine(database_url)
    assert "transactions" not in inspect(engine).get_table_names()
    engine.dispose()


def test_migrations_prefer_unpooled_database_url(tmp_path, monkeypatch):
    pooled_url = f"sqlite+pysqlite:///{(tmp_path / 'pooled.db').as_posix()}"
    unpooled_url = f"sqlite+pysqlite:///{(tmp_path / 'unpooled.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", pooled_url)
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", unpooled_url)
    monkeypatch.chdir(tmp_path)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    command.upgrade(config, "head")

    pooled_engine = make_engine(pooled_url)
    unpooled_engine = make_engine(unpooled_url)
    assert "users" not in inspect(pooled_engine).get_table_names()
    assert "users" in inspect(unpooled_engine).get_table_names()
    pooled_engine.dispose()
    unpooled_engine.dispose()
