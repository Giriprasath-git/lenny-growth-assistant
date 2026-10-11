"""
Health and readiness diagnostics endpoints.
Explicitly distinguishes application liveness from database readiness.
Guarantees the system does not misleadingly report readiness when PostgreSQL is unavailable.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Response, status

from backend.app.core.config import settings
from backend.app.db.session import check_database_health

try:
    import psutil
except ImportError:
    psutil = None  # Graceful fallback if psutil is not yet installed in dev

router = APIRouter()


# ------------------------------------------------------------------------------
# 1. GET /health/live - Application Liveness Probe
# ------------------------------------------------------------------------------
@router.get(
    "/health/live",
    summary="Application Liveness Probe",
    tags=["Health & Diagnostics"],
)
async def get_liveness() -> Dict[str, Any]:
    """
    Kubernetes/container liveness probe.
    Confirms the FastAPI ASGI process is alive and responsive.
    Does not probe external services.
    """
    return {
        "status": "alive",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ------------------------------------------------------------------------------
# 2. GET /health/ready - Database Readiness Probe
# ------------------------------------------------------------------------------
@router.get(
    "/health/ready",
    summary="Database Readiness Probe",
    tags=["Health & Diagnostics"],
)
async def get_readiness(response: Response) -> Dict[str, Any]:
    """
    Database readiness probe.
    Executes a SELECT 1 query against PostgreSQL.
    Returns HTTP 200 when PostgreSQL is responsive.
    Returns HTTP 503 (Service Unavailable) when PostgreSQL is unreachable.
    """
    is_ready, details = await check_database_health(timeout_seconds=3.0)

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "ready": False,
            "database": "unavailable",
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "status": "ready",
        "ready": True,
        "database": "connected",
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ------------------------------------------------------------------------------
# 3. GET /health - Comprehensive System Health & Diagnostics
# ------------------------------------------------------------------------------
@router.get(
    "/health",
    summary="Comprehensive System Health & Diagnostics",
    tags=["Health & Diagnostics"],
)
async def get_health(response: Response) -> Dict[str, Any]:
    """
    Aggregates application status, host memory diagnostics, active LLM providers,
    and PostgreSQL readiness. Sets HTTP 503 if the database is disconnected.
    """
    db_ready, db_details = await check_database_health(timeout_seconds=3.0)

    memory_info: Dict[str, Any] = {"available": "psutil_not_loaded"}
    if psutil:
        try:
            vm = psutil.virtual_memory()
            memory_info = {
                "total_mb": round(vm.total / (1024 * 1024), 2),
                "available_mb": round(vm.available / (1024 * 1024), 2),
                "used_mb": round(vm.used / (1024 * 1024), 2),
                "percent_used": vm.percent,
                "ram_warning": vm.percent > settings.MAX_SYSTEM_RAM_USAGE_PERCENT,
            }
        except Exception as exc:
            memory_info = {"error": str(exc)}

    # If the database is down, report degraded / HTTP 503
    overall_status = "healthy" if db_ready else "degraded"
    if not db_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall_status,
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "connected": db_ready,
            "status": "connected" if db_ready else "disconnected",
            "details": db_details,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
        },
        "providers": {
            "default": settings.DEFAULT_LLM_PROVIDER,
            "agent_framework": settings.AGENT_FRAMEWORK,
            "cloud_gemini": {
                "configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip()),
                "model": settings.GEMINI_MODEL,
                "free_tier_eligible": True,
            },
            "cloud_anthropic": {
                "configured": bool(settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY.strip()),
                "model": settings.ANTHROPIC_MODEL,
            },
            "local_ollama": {
                "base_url": settings.OLLAMA_BASE_URL,
                "model": settings.OLLAMA_MODEL,
                "timeout_seconds": settings.OLLAMA_REQUEST_TIMEOUT,
            },
        },
        "rag": {
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "embedding_model": settings.EMBEDDING_MODEL,
            "dimension": settings.EMBEDDING_DIMENSION,
        },
        "system_resources": memory_info,
    }
