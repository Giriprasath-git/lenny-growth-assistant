"""
Pytest configuration and isolated async test fixtures.
Guarantees tests never connect to the production PostgreSQL database.
Provides SQLite in-memory async engine, type compilation overrides, and simulated failure fixtures.
"""

import json
from pathlib import Path
import sqlite3
import sys
from typing import AsyncGenerator
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

# Ensure workspace root and backend root are both on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
for root_path in (str(PROJECT_ROOT), str(BACKEND_ROOT)):
    if root_path not in sys.path:
        sys.path.insert(0, root_path)

from backend.app.db.base import Base
from backend.app.db.models.transcript import Vector as FallbackVector
from backend.app.db.session import get_db
from backend.app.main import app

# ------------------------------------------------------------------------------
# SQLite Compatibility Adapters & Compilers for PostgreSQL Types
# ------------------------------------------------------------------------------
# Register DBAPI adapters for Python native types on SQLite
sqlite3.register_adapter(uuid.UUID, str)
sqlite3.register_adapter(dict, json.dumps)
sqlite3.register_adapter(list, json.dumps)


@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


# Compile Vector type safely to BLOB on SQLite (for test schema creation)
@compiles(FallbackVector, "sqlite")
def compile_fallback_vector_sqlite(type_, compiler, **kw):
    return "BLOB"


try:
    from pgvector.sqlalchemy import Vector

    @compiles(Vector, "sqlite")
    def compile_vector_sqlite(type_, compiler, **kw):
        return "BLOB"
except ImportError:
    pass


# ------------------------------------------------------------------------------
# Isolated In-Memory Async Database for Testing
# ------------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated database schema backed by in-memory SQLite for each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with TestingSessionLocal() as session:
            yield session
    finally:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(test_db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP client fixture with get_db overridden to use an isolated transactional session
    from the in-memory SQLite engine. Commits changes on success and cleans up per request.
    Guarantees zero communication with external or production PostgreSQL instances.
    """
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestingSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_with_db_failure() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client fixture simulating total database unavailability / connection failure."""
    from sqlalchemy.exc import OperationalError

    async def broken_get_db() -> AsyncGenerator[AsyncSession, None]:
        raise OperationalError("Connection refused by PostgreSQL server", {}, Exception())
        yield  # unreachable

    app.dependency_overrides[get_db] = broken_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def isolate_test_settings(monkeypatch):
    """
    Guarantees deterministic test execution isolated from the developer's local .env file.
    Enforces local Ollama default configuration per Phase 4A/4B requirements.
    """
    from backend.app.core.config import settings
    monkeypatch.setattr(settings, "DEFAULT_LLM_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "OLLAMA_REQUEST_TIMEOUT", 180)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite")

