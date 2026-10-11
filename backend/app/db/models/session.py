"""
ChatSession database model.
Tracks conversation threads, user preferences, JSONB metadata, and active skills.
"""

import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.message import ChatMessage
    from backend.app.db.models.artifact import Artifact


class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="New Conversation",
    )
    user_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ollama",  # 'ollama' or 'cloud'
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="qwen2.5:1.5b",
    )
    active_skill: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,  # 'ship30' or None
    )

    # Relationships
    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
        lazy="selectin",
    )
    artifacts: Mapped[List["Artifact"]] = relationship(
        "Artifact",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Artifact.created_at.asc()",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_chat_sessions_updated_at_desc", "updated_at"),
        Index("ix_chat_sessions_created_at_desc", "created_at"),
    )
