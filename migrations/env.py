"""
Alembic environment configuration.

- DATABASE_URL is read from app settings (env var) so no credentials
  are hardcoded in alembic.ini or this file.
- All models are imported via app.models so that autogenerate can detect
  schema changes automatically.
- Supports both 'online' (direct DB) and 'offline' (SQL script) modes.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Load alembic's own logging config from alembic.ini
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ── Import all models so Base.metadata is populated ───────────────────────────
# This must happen before `target_metadata` is set.
import app.models  # noqa: F401  # registers all ORM models
from app.models.base import Base

target_metadata = Base.metadata

# ── Override sqlalchemy.url from application settings ─────────────────────────
from app.config.settings import get_settings as _get_settings

_db_url = _get_settings().DATABASE_URL
config.set_main_option("sqlalchemy.url", _db_url)


# ── Offline mode ──────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations without an actual DB connection — emit SQL to stdout.
    Useful for generating SQL scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────

def run_migrations_online() -> None:
    """
    Run migrations against a live database connection.
    Uses NullPool so the migration process doesn't hold connections open.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _db_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    logger.info("Running migrations in offline mode")
    run_migrations_offline()
else:
    logger.info("Running migrations in online mode")
    run_migrations_online()
