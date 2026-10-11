"""
Chat Session and Message REST API endpoints under /api/v1/sessions.
Implements CRUD for conversation threads and message persistence with strict session isolation.
"""

from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.exceptions import SessionNotFoundError
from backend.app.core.logging import logger
from backend.app.db.models.message import ChatMessage
from backend.app.db.models.session import ChatSession
from backend.app.db.session import get_db
from backend.app.schemas.session import (
    MessageCreateRequest,
    MessageResponse,
    SessionCreateRequest,
    SessionListResponse,
    SessionResponse,
    SessionWithMessagesResponse,
)

router = APIRouter()


# ------------------------------------------------------------------------------
# 1. POST /sessions - Create Session
# ------------------------------------------------------------------------------
@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation session",
)
async def create_session(
    payload: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    """Creates a new ChatSession record in PostgreSQL with default or custom metadata."""
    chosen_provider = payload.provider or settings.DEFAULT_LLM_PROVIDER
    if chosen_provider in ("cloud", "gemini"):
        default_model = settings.GEMINI_MODEL
    elif chosen_provider == "anthropic":
        default_model = settings.ANTHROPIC_MODEL
    else:
        default_model = settings.OLLAMA_MODEL
    model_name = payload.model_name or default_model

    new_session = ChatSession(
        title=payload.title or "New Conversation",
        user_metadata=payload.user_metadata or {},
        provider=chosen_provider,
        model_name=model_name,
        active_skill=payload.active_skill,
    )
    db.add(new_session)
    await db.flush()
    await db.refresh(new_session)

    logger.info("Created new chat session: %s (provider=%s)", str(new_session.id), new_session.provider)
    return new_session


# ------------------------------------------------------------------------------
# 2. GET /sessions - List Sessions with Pagination
# ------------------------------------------------------------------------------
@router.get(
    "",
    response_model=SessionListResponse,
    summary="List paginated chat sessions",
)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=100, description="Max number of sessions to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    """Returns a paginated list of chat sessions, ordered by most recently updated."""
    # Count total
    count_query = select(func.count(ChatSession.id))
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Query items ordered by updated_at descending
    query = (
        select(ChatSession)
        .order_by(ChatSession.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    return SessionListResponse(
        items=[SessionResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ------------------------------------------------------------------------------
# 3. GET /sessions/{session_id} - Retrieve Session and Messages
# ------------------------------------------------------------------------------
@router.get(
    "/{session_id}",
    response_model=SessionWithMessagesResponse,
    summary="Retrieve session details and all associated messages",
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    """
    Retrieves a session and its chronological message stream.
    Strictly filters messages by session_id to guarantee session isolation.
    """
    query = (
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(
            selectinload(ChatSession.messages).selectinload(ChatMessage.citations)
        )
    )
    result = await db.execute(query)
    session_obj = result.scalar_one_or_none()

    if not session_obj:
        raise SessionNotFoundError(str(session_id))

    return session_obj


# ------------------------------------------------------------------------------
# 4. DELETE /sessions/{session_id} - Delete Session
# ------------------------------------------------------------------------------
@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session and all its messages",
)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Deletes the session and relies on database ON DELETE CASCADE
    to remove child messages, citations, and artifacts cleanly.
    """
    query = select(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(query)
    session_obj = result.scalar_one_or_none()

    if not session_obj:
        raise SessionNotFoundError(str(session_id))

    await db.delete(session_obj)
    await db.flush()
    logger.info("Deleted chat session: %s", str(session_id))
    return None


# ------------------------------------------------------------------------------
# 5. POST /sessions/{session_id}/messages - Store Message in Session
# ------------------------------------------------------------------------------
@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store a user message in an existing session",
)
async def create_session_message(
    session_id: uuid.UUID,
    payload: MessageCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatMessage:
    """
    Persists a user or system message within the specified session.
    Verifies that the session exists before persisting, preventing orphan messages.
    Does NOT invoke LLM inference or generate fake assistant responses (reserved for Phase 3).
    """
    # Verify session existence
    session_query = select(ChatSession).where(ChatSession.id == session_id)
    session_result = await db.execute(session_query)
    session_obj = session_result.scalar_one_or_none()

    if not session_obj:
        raise SessionNotFoundError(str(session_id))

    # Persist the message
    new_message = ChatMessage(
        session_id=session_id,
        role=payload.role,
        content=payload.content,
        provider_metadata=payload.provider_metadata or {},
    )
    db.add(new_message)

    # Bump session updated_at timestamp
    session_obj.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(new_message)

    logger.info("Persisted message %s in session %s (role=%s)", str(new_message.id), str(session_id), payload.role)
    return new_message


# ------------------------------------------------------------------------------
# 6. GET /sessions/{session_id}/messages - List Messages in Session
# ------------------------------------------------------------------------------
@router.get(
    "/{session_id}/messages",
    response_model=List[MessageResponse],
    summary="List all messages in a session ordered chronologically",
)
async def list_session_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[ChatMessage]:
    """
    Returns the chronological message stream for a specific session.
    Strictly filters by session_id to guarantee session isolation.
    """
    # Verify session existence
    session_query = select(ChatSession).where(ChatSession.id == session_id)
    session_result = await db.execute(session_query)
    session_obj = session_result.scalar_one_or_none()

    if not session_obj:
        raise SessionNotFoundError(str(session_id))

    query = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .options(selectinload(ChatMessage.citations))
        .order_by(ChatMessage.created_at.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


# ------------------------------------------------------------------------------
# 7. GET /sessions/{session_id}/artifacts - List Artifacts in Session
# ------------------------------------------------------------------------------
@router.get(
    "/{session_id}/artifacts",
    response_model=List[dict],
    summary="List all artifacts generated in a session",
)
async def list_session_artifacts(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Returns all artifacts generated in a specific session."""
    from backend.app.agent.artifact_service import ArtifactGenerationService
    service = ArtifactGenerationService()
    res = await service.list_session_artifacts(session_id, db)
    return [item.model_dump() for item in res.items]

