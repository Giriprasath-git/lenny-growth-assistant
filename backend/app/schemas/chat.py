"""
Pydantic request and response schemas for AI Agent Chat turns and Grounded Q&A.
"""

from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.session import CitationResponse, MessageResponse


class ChatTurnRequest(BaseModel):
    """Payload for submitting a conversation turn to the Grounded AI Agent."""
    session_id: uuid.UUID = Field(..., description="ID of the chat session thread")
    message: str = Field(..., min_length=1, max_length=10000, description="User prompt or question")
    provider: Optional[Literal["ollama", "cloud", "gemini", "anthropic", "pi_agent"]] = Field(
        default=None,
        description="Optional model provider override (defaults to settings.DEFAULT_LLM_PROVIDER: 'ollama' or 'pi_agent')",
    )
    model: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional model identifier override (e.g. 'qwen2.5:1.5b')",
    )
    active_skill: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional active skill (e.g. 'ship30')",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of transcript evidence chunks to retrieve",
    )


class ChatTurnResponse(BaseModel):
    """Structured response returned after executing a grounded chat turn."""
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
    citations: List[CitationResponse] = Field(default_factory=list)
    provider: str
    model: str
    latency_ms: float
    grounded_chunk_count: int = 0
    framework: Optional[str] = None
    is_sdk: bool = False
