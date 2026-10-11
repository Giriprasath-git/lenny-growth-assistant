"""
TranscriptChunk database model.
Stores segmented podcast transcript excerpts with speaker metadata and vector embeddings.
"""

import uuid
from typing import Any, Dict
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin

# Safe import for pgvector
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Type fallback during pre-installation / initial scaffolding
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):  # type: ignore
        def __init__(self, dim: int):
            self.dim = dim

        def get_col_spec(self, **kw):
            return f"vector({self.dim})"


class TranscriptChunk(Base, TimestampMixin):
    """
    TranscriptChunk database model.
    Stores podcast transcript segments and metadata.

    PHASE 2 ARCHITECTURE:
    Persists transcript metadata only (episode, speaker, timing, text content, JSONB metadata).
    Establishes clean relational integrity and foreign key target for MessageCitation (chunk_id).
    
    DEFERRED TO PHASE 3:
    The `embedding` column (`Vector(768)`) and HNSW vector index (`idx_transcript_chunks_embedding`)
    are intentionally deferred to Phase 3 (Transcript Ingestion & pgvector Storage).
    Phase 3 will initialize the `vector` PostgreSQL extension and add the vector column via
    a dedicated Alembic migration without breaking Phase 2 session persistence.
    """
    __tablename__ = "transcript_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    episode_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    episode_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    guest_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    timestamp_start: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    timestamp_end: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
