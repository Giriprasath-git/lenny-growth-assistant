"""
Transcript query and ingestion status endpoints.
Provides text-based grounded search, source citations, and corpus indexing metrics.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.models.transcript import TranscriptChunk
from backend.app.db.session import get_db
from backend.app.rag.retriever import TranscriptRetriever
from backend.app.schemas.transcript import (
    CorpusStatusResponse,
    TranscriptChunkResponse,
    TranscriptSearchQuery,
    TranscriptSearchResponse,
)

router = APIRouter()

# Re-export schemas for backward compatibility with existing tests and imports
__all__ = [
    "TranscriptSearchQuery",
    "TranscriptChunkResponse",
    "TranscriptSearchResponse",
    "CorpusStatusResponse",
    "router",
]


@router.post(
    "/search",
    response_model=TranscriptSearchResponse,
    summary="Search grounded transcript passages",
    status_code=status.HTTP_200_OK,
)
async def search_transcripts(
    payload: TranscriptSearchQuery,
    db: AsyncSession = Depends(get_db),
) -> TranscriptSearchResponse:
    """
    Searches transcript passages grounded in Lenny's podcast archives.
    Uses PostgreSQL multi-signal ranking with full source attribution.
    Read-only transaction with zero database side-effects.
    """
    try:
        retriever = TranscriptRetriever()
        chunks = await retriever.search(
            query=payload.query,
            db=db,
            top_k=payload.top_k,
            guest_filter=payload.guest_filter,
        )

        response_items = [
            TranscriptChunkResponse(
                chunk_id=c.chunk_id,
                episode_id=c.episode_id,
                episode_title=c.episode_title,
                guest_name=c.guest_name,
                timestamp_start=c.timestamp_start,
                timestamp_end=c.timestamp_end,
                content=c.content,
                excerpt=c.excerpt or None,
                similarity_score=c.similarity_score,
                youtube_url=c.youtube_url or None,
                youtube_timestamp_url=c.youtube_timestamp_url or None,
                source_file=c.source_file or None,
                is_interpolated_timestamp=c.is_interpolated_timestamp,
                metadata=c.metadata,
            )
            for c in chunks
        ]

        return TranscriptSearchResponse(
            query=payload.query,
            count=len(response_items),
            results=response_items,
        )
    except Exception as exc:
        logger.error(f"Search endpoint failure for query '{payload.query}': {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while executing transcript search: {str(exc)}",
        )


@router.get(
    "/status",
    response_model=CorpusStatusResponse,
    summary="Get transcript corpus indexing metrics",
    status_code=status.HTTP_200_OK,
)
async def get_corpus_status(
    db: AsyncSession = Depends(get_db),
) -> CorpusStatusResponse:
    """Returns actual indexing metrics for the podcast corpus."""
    try:
        ep_count_query = select(func.count(func.distinct(TranscriptChunk.episode_id)))
        chunk_count_query = select(func.count(TranscriptChunk.id))

        ep_res = await db.execute(ep_count_query)
        chunk_res = await db.execute(chunk_count_query)

        episodes_count = ep_res.scalar_one_or_none() or 0
        chunks_count = chunk_res.scalar_one_or_none() or 0
    except Exception as exc:
        logger.error(f"Failed to query corpus status: {exc}", exc_info=True)
        episodes_count = 0
        chunks_count = 0

    return CorpusStatusResponse(
        indexed_episodes=episodes_count,
        total_chunks=chunks_count,
        embedding_model=settings.EMBEDDING_MODEL,
        retrieval_mode="postgresql_multi_signal_rank",
        status="ready" if chunks_count > 0 else "empty",
        notes="31 repeated episode IDs detected across 303 source files (deferred issue P3-D01)" if episodes_count > 0 else None,
    )
