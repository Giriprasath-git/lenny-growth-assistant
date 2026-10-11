"""
Alembic migration environment configured for asynchronous SQLAlchemy 2.0 and asyncpg.
Discovers all application models via Base.metadata.
"""

import asyncio
from logging.config import fileConfig
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure both project root and backend root are on sys.path
# This guarantees that 'from backend.app...' resolves cleanly
# whether alembic is invoked from the workspace root or the backend/ directory
BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent

for root_path in (str(PROJECT_ROOT), str(BACKEND_ROOT)):
    if root_path not in sys.path:
        sys.path.insert(0, root_path)

# Import settings and application models for metadata discovery
from backend.app.core.config import settings
from backend.app.db.base import Base
# Importing all models registers them onto Base.metadata
from backend.app.db.models import (
    Artifact,
    ChatMessage,
    ChatSession,
    MessageCitation,
    TranscriptChunk,
)

config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata object for autogenerate support
target_metadata = Base.metadata

# Inject database URL from application settings (ignoring hardcoded ini url)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode without an active DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Creates an async engine and executes migrations in an async worker loop."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncio event loop."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
