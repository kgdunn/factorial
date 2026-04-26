from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.db.base import Base

config = context.config

# Skip Alembic's own logging setup when invoked programmatically with a
# URL override (i.e. by ``backend/tests/conftest.py``). ``fileConfig``
# defaults to ``disable_existing_loggers=True``, which would silence the
# app's loggers — including ``caplog`` capture in unrelated tests. CLI
# invocations (``make migrate``, plain ``alembic upgrade head``) keep
# the standard alembic.ini-driven logging.
_url_override = config.get_main_option("sqlalchemy.url")
if _url_override is None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    """Pick the database URL Alembic should target.

    Honour ``sqlalchemy.url`` if a caller set it programmatically (e.g.
    the test conftest pointing at the test database); otherwise fall
    back to the production ``database_url_sync``. Keeps ``make migrate``
    and a bare ``alembic upgrade head`` working unchanged.
    """
    return _url_override or settings.database_url_sync


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the database)."""
    connectable = create_engine(_resolve_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
