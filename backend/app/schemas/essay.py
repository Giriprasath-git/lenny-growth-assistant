"""
Pydantic schemas for Ship 30 for 30 Essay Generation and Retrieval.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.session import CitationResponse


EssayTone = Literal["educational", "conversational", "professional", "storytelling"]
EssayLength = Literal["short", "medium", "deep_dive"]


class EssayGenerateRequest(BaseModel):
    """Request payload for generating a Ship 30 for 30 atomic essay."""
    topic: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Central topic, thesis, or question for the essay",
        examples=["Elena Verna's Product-Led Growth Retention Loops"],
    )
    target_audience: Optional[str] = Field(
        default="Product Managers, Founders, & Growth Operators",
        max_length=200,
        description="Target readership demographic or professional tier",
    )
    tone: Optional[EssayTone] = Field(
        default="educational",
        description="Stylistic writing tone (educational, conversational, professional, storytelling)",
    )
    desired_length: Optional[EssayLength] = Field(
        default="deep_dive",
        description="Target essay depth: 'short' (~300w), 'medium' (~600w), 'deep_dive' (~1,000-1,250w)",
    )
    specific_instructions: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional custom nuances, sections to include, or constraints",
    )
    ground_with_podcasts: bool = Field(
        default=True,
        description="Whether to retrieve and ground the essay in Lenny Rachitsky's podcast transcript archives",
    )
    session_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional existing chat session ID to associate this essay with for persistence",
    )
    provider: Optional[Literal["ollama", "cloud", "gemini", "anthropic", "pi_agent"]] = Field(
        default=None,
        description="Optional LLM provider override ('ollama' default, 'cloud', or 'pi_agent')",
    )
    model: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional model identifier override (e.g. 'qwen2.5:1.5b')",
    )


class EssayResponse(BaseModel):
    """Structured response representing a generated Ship 30 essay."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    title: str
    content: str
    headline_hook: Optional[str] = None
    alternative_titles: List[str] = Field(default_factory=list)
    takeaway: Optional[str] = None
    topic: str
    target_audience: str
    tone: str
    desired_length: str
    requested_word_count: int
    actual_word_count: int
    word_count_status: str = Field(
        default="target_achieved",
        description="'target_achieved' or 'bounded_by_model_output'",
    )
    word_count_note: Optional[str] = None
    provider: str
    model: str
    latency_ms: float
    podcast_grounded: bool
    citations: List[CitationResponse] = Field(default_factory=list)
    created_at: datetime


class EssayListResponse(BaseModel):
    """Paginated list of saved essays."""
    items: List[EssayResponse]
    total: int
