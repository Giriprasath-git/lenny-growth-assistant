"""
Pydantic schemas for transcript retrieval, source attribution, and corpus status.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TranscriptSearchQuery(BaseModel):
    """Payload for grounded transcript search requests."""
    query: str = Field(
        default="",
        description="Natural language or keyword search query string",
        max_length=500,
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of relevant chunks to return",
    )
    guest_filter: Optional[str] = Field(
        default=None,
        description="Optional filter to restrict search to a specific guest name",
        max_length=200,
    )


class TranscriptChunkResponse(BaseModel):
    """Individual grounded transcript chunk with complete source attribution."""
    chunk_id: str = Field(..., description="Unique chunk UUID identifier")
    episode_id: str = Field(..., description="Canonical episode identifier (e.g. yt-dQw4w9WgXcQ)")
    episode_title: str = Field(..., description="Episode title")
    guest_name: str = Field(..., description="Guest name")
    timestamp_start: str = Field(..., description="Start timestamp string (HH:MM:SS)")
    timestamp_end: str = Field(..., description="End timestamp string (HH:MM:SS)")
    content: str = Field(..., description="Transcript dialogue excerpt")
    excerpt: Optional[str] = Field(default=None, description="Concise match snippet centered on query terms")
    similarity_score: float = Field(..., description="Normalized relevance score between 0.0 and 1.0")
    youtube_url: Optional[str] = Field(default=None, description="Episode YouTube URL")
    youtube_timestamp_url: Optional[str] = Field(default=None, description="Direct deep-link to YouTube timestamp")
    source_file: Optional[str] = Field(default=None, description="Repository-relative source transcript path")
    is_interpolated_timestamp: bool = Field(default=False, description="Whether timestamp is interpolated from monologue")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Supplementary source metadata")


class TranscriptSearchResponse(BaseModel):
    """Response payload for transcript search queries."""
    query: str = Field(..., description="Original search query string")
    count: int = Field(..., description="Number of retrieved results")
    results: List[TranscriptChunkResponse] = Field(
        default_factory=list,
        description="Ranked list of retrieved transcript chunks",
    )


class CorpusStatusResponse(BaseModel):
    """Indexing metrics and corpus readiness status."""
    indexed_episodes: int = Field(..., description="Count of distinct indexed canonical episode IDs")
    total_chunks: int = Field(..., description="Total count of stored transcript chunks in PostgreSQL")
    embedding_model: str = Field(..., description="Configured embedding model identifier")
    retrieval_mode: str = Field(..., description="Active retrieval engine mode (e.g. postgresql_fts_hybrid)")
    status: str = Field(..., description="Readiness status ('ready' or 'empty')")
    notes: Optional[str] = Field(default=None, description="Operational notes or deferred issue references")
