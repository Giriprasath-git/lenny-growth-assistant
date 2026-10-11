"""
ChatMessage and MessageCitation database models.
Stores conversation turns and grounded citation links with explicit session isolation.
"""

import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.session import ChatSession
    from backend.app.db.models.transcript import TranscriptChunk


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,  # 'user', 'assistant', 'system'
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    provider_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship(
        "ChatSession",
        back_populates="messages",
    )
    citations: Mapped[List["MessageCitation"]] = relationship(
        "MessageCitation",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageCitation.citation_index.asc()",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_chat_messages_role",
        ),
        # Composite index ensuring strict session isolation and ordered timeline querying
        Index("ix_chat_messages_session_id_created_at", "session_id", "created_at"),
    )


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcript_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    citation_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    episode_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    episode_title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    guest_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    timestamp_start: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    timestamp_end: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    quoted_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    relevance_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    # Relationships
    message: Mapped["ChatMessage"] = relationship(
        "ChatMessage",
        back_populates="citations",
    )
    chunk: Mapped[Optional["TranscriptChunk"]] = relationship(
        "TranscriptChunk",
    )

    __table_args__ = (
        Index("ix_message_citations_message_id_citation_index", "message_id", "citation_index"),
    )
