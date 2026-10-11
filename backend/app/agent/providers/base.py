"""
Base interface for LLM provider adapters.
Standardizes generation and streaming contracts across Cloud and Local Ollama models.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional


@dataclass
class ChatMessageInput:
    role: str  # 'system', 'user', 'assistant'
    content: str


@dataclass
class StreamDelta:
    delta_text: str = ""
    is_complete: bool = False
    finish_reason: Optional[str] = None
    extra_metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class CompletionResult:
    content: str
    total_tokens: int = 0
    model_name: str = ""
    finish_reason: str = "completed"
    latency_ms: float = 0.0
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def model(self) -> str:
        """Alias property for model_name."""
        return self.model_name


class BaseLLMProvider(ABC):
    """Abstract interface that all provider adapters (Cloud / Ollama) must satisfy."""

    @abstractmethod
    async def generate(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> CompletionResult:
        """Executes a non-streaming completion."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> AsyncGenerator[StreamDelta, None]:
        """Yields streaming tokens as they arrive."""
        pass

    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """Checks if the provider endpoint/credentials are healthy and reachable."""
        pass
