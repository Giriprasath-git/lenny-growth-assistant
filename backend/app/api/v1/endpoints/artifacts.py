"""
FastAPI REST endpoints for Artifact Generation, Retrieval, and Secure Downloads.
Provides versioned routes for Markdown documents and sandboxed HTML/CSS deliverables.
"""

import re
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.artifact_service import ArtifactGenerationService
from backend.app.core.exceptions import (
    IncompleteArtifactError,
    ProviderUnavailableError,
    SessionNotFoundError,
)
from backend.app.core.logging import logger
from backend.app.db.models.artifact import Artifact
from backend.app.db.session import get_db
from backend.app.schemas.artifact import (
    ArtifactGenerateRequest,
    ArtifactListResponse,
    ArtifactResponse,
)

router = APIRouter()
artifact_service = ArtifactGenerationService()


def _sanitize_filename(title: str, artifact_type: str, artifact_id: uuid.UUID) -> str:
    """Produces a path-traversal-proof, safe download filename."""
    # Strip any directory traversal sequences and non-safe characters
    cleaned = re.sub(r"[^a-zA-Z0-9_\- ]", "", title).strip()
    cleaned = cleaned.replace(" ", "_")
    if not cleaned:
        cleaned = f"artifact_{str(artifact_id)[:8]}"

    ext = "html" if artifact_type.lower() == "html" else "md"
    return f"{cleaned}.{ext}"


@router.post(
    "",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate and persist a new artifact",
    description="Synthesizes a publication-grade Markdown document or self-contained HTML/CSS deliverable.",
)
@router.post(
    "/generate",
    response_model=ArtifactResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def generate_artifact_endpoint(
    request: ArtifactGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    """Generates an artifact from conversation context, message, or custom content."""
    try:
        return await artifact_service.generate_artifact(request, db)
    except IncompleteArtifactError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.message,
        )
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session not found: {e.session_id}",
        )
    except ProviderUnavailableError as e:
        raise HTTPException(
            status_code=e.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=e.detail,
        )
    except Exception as e:
        logger.error(f"Unexpected artifact generation failure: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate artifact. Please try again or check local provider status.",
        )


@router.get(
    "/{artifact_id}",
    response_model=ArtifactResponse,
    summary="Retrieve an artifact by ID",
)
async def get_artifact_endpoint(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ArtifactResponse:
    """Retrieves a previously generated artifact by its unique ID."""
    artifact = await artifact_service.get_artifact(artifact_id, db)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
        )
    return artifact


@router.get(
    "",
    response_model=ArtifactListResponse,
    summary="List artifacts",
    description="Lists artifacts, optionally filtered by session ID.",
)
async def list_artifacts_endpoint(
    session_id: Optional[uuid.UUID] = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ArtifactListResponse:
    """Returns artifacts for a session or recent global artifacts."""
    if session_id:
        return await artifact_service.list_session_artifacts(session_id, db, limit=limit, offset=offset)

    # General query across sessions
    stmt = (
        select(Artifact)
        .options(selectinload(Artifact.session))
        .order_by(desc(Artifact.created_at))
        .offset(offset)
        .limit(limit)
    )
    res = await db.execute(stmt)
    artifacts = res.scalars().all()

    items = [
        ArtifactResponse(
            id=a.id,
            session_id=a.session_id,
            message_id=a.message_id,
            artifact_type=a.artifact_type,
            title=a.title,
            content=a.content,
            provider=a.session.provider if a.session else "ollama",
            model_name=a.session.model_name if a.session else "qwen2.5:1.5b",
            created_at=a.created_at,
            is_sanitized=True,
            security_policy={"sandbox": "script-disabled", "csp_enforced": True},
            metadata={"length_chars": len(a.content)},
        )
        for a in artifacts
    ]
    return ArtifactListResponse(items=items, total=len(items))


@router.get(
    "/{artifact_id}/download",
    summary="Download artifact file securely",
    description="Downloads the artifact as a .md or .html file with attachment disposition and security headers.",
)
async def download_artifact_endpoint(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Serves the artifact content as a downloadable file.
    Uses Content-Disposition: attachment to guarantee the browser does not execute
    or render the HTML content under the API host origin.
    """
    stmt = select(Artifact).where(Artifact.id == artifact_id)
    res = await db.execute(stmt)
    artifact = res.scalar_one_or_none()
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
        )

    safe_filename = _sanitize_filename(artifact.title, artifact.artifact_type, artifact.id)
    media_type = "text/html; charset=utf-8" if artifact.artifact_type.lower() == "html" else "text/markdown; charset=utf-8"

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }

    return Response(
        content=artifact.content,
        media_type=media_type,
        headers=headers,
    )


@router.delete(
    "/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an artifact",
)
async def delete_artifact_endpoint(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deletes an artifact by ID."""
    deleted = await artifact_service.delete_artifact(artifact_id, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact {artifact_id} not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
