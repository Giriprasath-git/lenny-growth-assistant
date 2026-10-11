"""
Automated unit tests for Health, Liveness, and Readiness probes.
Verifies that:
- /health/live returns HTTP 200 without checking external services.
- /health/ready returns HTTP 200 when PostgreSQL is responsive.
- /health/ready returns HTTP 503 when PostgreSQL is unavailable.
- /health returns HTTP 503 and degraded status when PostgreSQL is unavailable.
"""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_endpoint(client: AsyncClient):
    """Verifies that GET /api/v1/health/live returns HTTP 200 and 'alive'."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_endpoint_when_db_connected(client: AsyncClient):
    """Verifies that GET /api/v1/health/ready returns HTTP 200 when database ping succeeds."""
    with patch(
        "backend.app.api.v1.endpoints.health.check_database_health",
        new=AsyncMock(return_value=(True, "PostgreSQL connection responsive (SELECT 1 succeeded)")),
    ):
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["ready"] is True
        assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_readiness_endpoint_when_db_disconnected(client: AsyncClient):
    """
    Verifies that GET /api/v1/health/ready returns HTTP 503 when database is unavailable.
    Guarantees the system does NOT misleadingly report ready when PostgreSQL is down.
    """
    with patch(
        "backend.app.api.v1.endpoints.health.check_database_health",
        new=AsyncMock(return_value=(False, "PostgreSQL unavailable: OperationalError")),
    ):
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["ready"] is False
        assert data["database"] == "unavailable"


@pytest.mark.asyncio
async def test_comprehensive_health_when_db_connected(client: AsyncClient):
    """Verifies that GET /api/v1/health returns HTTP 200 with full diagnostic telemetry when healthy."""
    with patch(
        "backend.app.api.v1.endpoints.health.check_database_health",
        new=AsyncMock(return_value=(True, "PostgreSQL connection responsive")),
    ):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"]["connected"] is True
        assert "providers" in data
        assert "system_resources" in data


@pytest.mark.asyncio
async def test_comprehensive_health_when_db_down(client: AsyncClient):
    """Verifies that GET /api/v1/health returns HTTP 503 and degraded status when database is disconnected."""
    with patch(
        "backend.app.api.v1.endpoints.health.check_database_health",
        new=AsyncMock(return_value=(False, "Connection timed out")),
    ):
        response = await client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"]["connected"] is False
        assert data["database"]["status"] == "disconnected"
