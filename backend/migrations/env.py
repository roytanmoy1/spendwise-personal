import os

from alembic import context

from app import models
from app.config import Settings
from app.db import make_engine

target_metadata = models.Base.metadata


def _migration_engine():
    database_url = os.environ.get("DATABASE_URL_UNPOOLED") or Settings().database_url
    return make_engine(database_url)


def run_migrations_offline():
    engine = _migration_engine()
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = _migration_engine()
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
