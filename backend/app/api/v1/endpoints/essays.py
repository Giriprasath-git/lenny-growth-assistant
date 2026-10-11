"""
Ship 30 for 30 Essay Generation REST API endpoints under /api/v1/essays.
Provides structured essay synthesis, podcast transcript grounding, and persistent retrieval.
"""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.essay_service import EssayGenerationService
from backend.app.core.exceptions import AppException, ProviderUnavailableError, SessionNotFoundError
from backend.app.core.logging import logger
from backend.app.db.session import get_db
from backend.app.schemas.essay import EssayGenerateRequest, EssayListResponse, EssayResponse

router = APIRouter()

# Reusable EssayGenerationService instance
essay_service = EssayGenerationService()


@router.post(
    "",
    response_model=EssayResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a Ship 30 for 30 atomic essay",
    description=(
        "Synthesizes a structured digital essay based on user topic, tone, audience, and length. "
        "Optionally retrieves and grounds insights from Lenny Rachitsky's podcast transcript archives."
    ),
)
async def generate_essay(
    payload: EssayGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> EssayResponse:
    """Generates a structured nonfiction essay and persists it to PostgreSQL."""
    try:
        essay = await essay_service.generate_essay(payload=payload, db=db)
        return essay
    except (SessionNotFoundError, ProviderUnavailableError) as domain_err:
        raise domain_err
    except Exception as e:
        logger.exception("Unexpected error during Ship 30 essay generation: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Essay generation failed: {str(e)}",
        )


@router.post(
    "/generate",
    response_model=EssayResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate essay (alias endpoint)",
    description="Compatible alias for POST /api/v1/essays.",
)
async def generate_essay_alias(
    payload: EssayGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> EssayResponse:
    """Alias endpoint routing to main essay generator."""
    return await generate_essay(payload=payload, db=db)


@router.get(
    "",
    response_model=EssayListResponse,
    summary="List recently generated Ship 30 essays",
)
async def list_essays(
    limit: int = Query(default=20, ge=1, le=100, description="Max essays to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
) -> EssayListResponse:
    """Returns a paginated list of previously generated essays."""
    return await essay_service.list_recent_essays(db=db, limit=limit, offset=offset)


@router.get(
    "/{essay_id}",
    response_model=EssayResponse,
    summary="Retrieve a generated essay by ID",
)
async def get_essay(
    essay_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EssayResponse:
    """Retrieves a previously generated essay by its message ID."""
    essay = await essay_service.get_essay_by_id(essay_id=essay_id, db=db)
    if not essay:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Essay with ID {essay_id} not found.",
        )
    return essay
