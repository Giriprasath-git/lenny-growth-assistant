"""
SQLAlchemy async engine, session lifecycle, and database health utilities.
Configured with connection pooling optimized for an 8 GB RAM development machine.
"""

import asyncio
from typing import AsyncGenerator, Tuple
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.config import settings
from backend.app.core.exceptions import DatabaseError
from backend.app.core.logging import logger

# ------------------------------------------------------------------------------
# Engine & Session Factory Configuration
# ------------------------------------------------------------------------------
# Conservative pool settings prevent memory exhaustion and socket starvation on 8 GB RAM
async_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # Discards stale or severed connections automatically
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ------------------------------------------------------------------------------
# FastAPI Session Dependency Injection
# ------------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an active async database session.
    Enforces transactional boundaries with automatic rollback on unhandled exceptions.
    """
    session: AsyncSession = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except SQLAlchemyError as err:
        await session.rollback()
        logger.error("Database transaction error: %s", str(err))
        raise DatabaseError(
            message="Database query or transaction execution failed.",
            details={"error_type": err.__class__.__name__},
        ) from err
    except Exception as exc:
        await session.rollback()
        raise exc
    finally:
        await session.close()


# ------------------------------------------------------------------------------
# Readiness & Diagnostic Probes
# ------------------------------------------------------------------------------
async def check_database_health(timeout_seconds: float = 3.0) -> Tuple[bool, str]:
    """
    Executes a lightweight diagnostic ping (SELECT 1) against PostgreSQL.
    Returns (is_ready, diagnostic_message).
    Guaranteed not to raise unhandled exceptions during readiness checks.
    """
    try:
        async with asyncio.timeout(timeout_seconds):
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True, "PostgreSQL connection responsive (SELECT 1 succeeded)"
    except asyncio.TimeoutError:
        logger.warning("Database readiness probe timed out after %.1fs", timeout_seconds)
        return False, f"PostgreSQL connection timed out ({timeout_seconds}s limit)"
    except SQLAlchemyError as err:
        logger.warning("Database readiness check failed: %s", str(err))
        return False, f"PostgreSQL unavailable: {err.__class__.__name__}"
    except Exception as exc:
        logger.warning("Unexpected error during database health check: %s", str(exc))
        return False, f"PostgreSQL connection error: {str(exc)}"


async def close_db_engine() -> None:
    """Closes all connection pools gracefully during application shutdown."""
    logger.info("Disposing async database connection pools...")
    await async_engine.dispose()
