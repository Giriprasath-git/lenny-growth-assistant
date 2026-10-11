"""
Pydantic schemas for Artifact Generation, Retrieval, and Download.
Defines contracts for Markdown documents and sandboxed HTML/CSS deliverables.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ArtifactType(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"


class ArtifactGenerateRequest(BaseModel):
    """Payload to request AI-powered artifact generation."""
    session_id: uuid.UUID = Field(
        ...,
        description="Target chat session ID originating the artifact",
    )
    message_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional source message ID (e.g. turning a specific answer into an artifact)",
    )
    artifact_type: ArtifactType = Field(
        ArtifactType.MARKDOWN,
        description="Desired format: 'markdown' for formatted document, 'html' for styled deliverable",
    )
    title: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional custom title. If omitted, synthesized from context.",
    )
    instructions: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional custom instructions (e.g. 'Turn into a 1-page PRD' or 'Create a growth loop flowchart')",
    )
    context_source: Optional[str] = Field(
        "session",
        description="Source of context: 'session' (recent history), 'message' (single message), 'custom', or 'essay'",
    )
    custom_content: Optional[str] = Field(
        None,
        max_length=25000,
        description="Optional explicit source text or essay content to format as an artifact",
    )
    provider: Optional[str] = Field(
        None,
        description="Model provider override: 'ollama' (default), 'cloud', or 'pi_agent'",
    )


class ArtifactResponse(BaseModel):
    """Structured response representing a persisted artifact."""
    id: uuid.UUID
    session_id: uuid.UUID
    message_id: Optional[uuid.UUID] = None
    artifact_type: str
    title: str
    content: str
    provider: str = "ollama"
    model_name: str = "qwen2.5:1.5b"
    created_at: datetime
    is_sanitized: bool = True
    security_policy: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ArtifactListResponse(BaseModel):
    """Paginated list of artifacts for a session or user."""
    items: List[ArtifactResponse]
    total: int
