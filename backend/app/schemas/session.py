"""
Pydantic schemas for Chat Sessions, Messages, and Grounded Citations.
Enforces strict validation, field limits, and response serialization.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------------------------------
# Citation Schemas
# ------------------------------------------------------------------------------
class CitationBase(BaseModel):
    citation_index: int = Field(default=1, ge=1, description="Sequential citation marker [1], [2], etc.")
    chunk_id: Optional[uuid.UUID] = Field(default=None, description="Referenced transcript chunk UUID")
    episode_id: Optional[str] = Field(default=None, max_length=100)
    episode_title: Optional[str] = Field(default=None, max_length=255)
    guest_name: Optional[str] = Field(default=None, max_length=255)
    timestamp_start: Optional[str] = Field(default=None, max_length=20)
    timestamp_end: Optional[str] = Field(default=None, max_length=20)
    quoted_text: str = Field(..., min_length=1, description="Verbatim transcript quote")
    relevance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CitationResponse(CitationBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


# ------------------------------------------------------------------------------
# Message Schemas
# ------------------------------------------------------------------------------
class MessageCreateRequest(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(
        default="user",
        description="Author role of the message",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Text content of the message",
    )
    provider_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional provider/model metadata (e.g. latency, tokens)",
    )


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    citations: List[CitationResponse] = Field(default_factory=list)


# ------------------------------------------------------------------------------
# Session Schemas
# ------------------------------------------------------------------------------
class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(
        default="New Conversation",
        min_length=1,
        max_length=255,
        description="Readable title for the conversation thread",
    )
    user_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Arbitrary user or client metadata stored as JSONB",
    )
    provider: Optional[str] = Field(
        default="ollama",
        max_length=50,
        description="LLM provider name: 'ollama' or 'cloud'",
    )
    model_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional model identifier override",
    )
    active_skill: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional active skill: e.g. 'ship30'",
    )


class SessionUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    user_metadata: Optional[Dict[str, Any]] = Field(default=None)
    active_skill: Optional[str] = Field(default=None, max_length=50)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    provider: str
    model_name: str
    active_skill: Optional[str]
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseModel):
    items: List[SessionResponse]
    total: int = Field(..., ge=0, description="Total number of sessions available")
    limit: int = Field(..., ge=1, description="Pagination page limit applied")
    offset: int = Field(..., ge=0, description="Pagination offset applied")


class SessionWithMessagesResponse(SessionResponse):
    model_config = ConfigDict(from_attributes=True)

    messages: List[MessageResponse] = Field(
        default_factory=list,
        description="Chronological stream of conversation messages belonging exclusively to this session",
    )
