from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.infrastructure.db.session import DATABASE_URL, Base
from app.infrastructure.db import models  # noqa

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

import os


def _is_placeholder(url: str | None) -> bool:
    if not url:
        return True
    u = url.strip()
    return (
        not u
        or u.startswith("driver://")
        or "driver://" in u
        or "user:pass@localhost/dbname" in u
    )


def _resolve_database_url() -> str:
    # 1. Environment-derived URL takes primary precedence
    env_url = os.getenv("DATABASE_URL")
    if env_url and not _is_placeholder(env_url):
        return env_url.strip()

    # 2. Config option if explicitly configured (e.g. by test runner) and not a placeholder
    config_url = config.get_main_option("sqlalchemy.url")
    if config_url and not _is_placeholder(config_url):
        return config_url.strip()

    # 3. Authoritative application database URL from session/settings
    if DATABASE_URL and not _is_placeholder(DATABASE_URL):
        return DATABASE_URL.strip()

    raise ValueError(
        "Alembic database URL is not configured or contains an unresolved placeholder. "
        "A valid DATABASE_URL must be provided."
    )


runtime_url = _resolve_database_url()
config.set_main_option("sqlalchemy.url", runtime_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
