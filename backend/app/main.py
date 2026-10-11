"""
FastAPI application entrypoint for The Lenny Growth Assistant.
Includes structured lifecycle hooks, CORS middleware, and centralized error handling.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.v1.router import api_v1_router
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException
from backend.app.core.logging import logger, setup_logging
from backend.app.db.session import close_db_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.
    Handles startup (logging init, pool configuration) and graceful shutdown.
    Avoids automatic table creation (Base.metadata.create_all) in favor of managed Alembic migrations.
    """
    setup_logging()
    logger.info("Initializing %s (v%s) in [%s] mode...", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    logger.info("Host constraints: 8 GB RAM target, workspace Drive D:")
    logger.info("Database URL configured: %s", settings.masked_database_url)
    logger.info("Active default provider: %s", settings.DEFAULT_LLM_PROVIDER)

    yield

    # Graceful shutdown: release database connection pools
    logger.info("Shutting down %s...", settings.APP_NAME)
    await close_db_engine()


def create_application() -> FastAPI:
    """Application factory for FastAPI server."""
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Grounded AI Conversational Assistant for Product & Growth, powered by Lenny's Podcast transcripts.",
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # --------------------------------------------------------------------------
    # CORS Configuration
    # --------------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------------------------
    # Global Exception Handlers
    # --------------------------------------------------------------------------
    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning("Request validation error on %s: %s", request.url.path, exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": True,
                "message": "Request validation failed.",
                "details": {"validation_errors": exc.errors()},
            },
        )

    @application.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.error("Domain exception on %s: %s (status %d)", request.url.path, exc.message, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "message": exc.message,
                "detail": exc.message,
                "details": exc.details,
            },
        )

    @application.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database operational exception on %s: %s", request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": True,
                "message": "Database operation failed or database is temporarily unavailable.",
                "details": {"error_type": exc.__class__.__name__} if settings.DEBUG else {},
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception on %s: %s", request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "message": "An unexpected internal server error occurred.",
                "details": {"type": exc.__class__.__name__} if settings.DEBUG else {},
            },
        )

    # --------------------------------------------------------------------------
    # Route Registration
    # --------------------------------------------------------------------------
    application.include_router(api_v1_router, prefix="/api")

    @application.get("/", include_in_schema=False)
    async def root_redirect():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "health_check": "/api/v1/health",
            "liveness_probe": "/api/v1/health/live",
            "readiness_probe": "/api/v1/health/ready",
            "documentation": "/api/docs" if settings.DEBUG else "disabled",
        }

    return application


app = create_application()
