"""
Embedding provider abstraction and vector readiness extension points.
Supports optional local Ollama embeddings (e.g. nomic-embed-text) while
ensuring the text retrieval baseline operates independently without requiring
an active embedding server or pgvector extension.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import httpx
from backend.app.core.config import settings
from backend.app.core.logging import logger


class BaseEmbeddingProvider(ABC):
    """Abstract interface for text embedding models."""

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """Generate embedding vector for a single search query."""
        pass

    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a batch of text chunks."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding dimension."""
        pass


class NullEmbeddingProvider(BaseEmbeddingProvider):
    """
    Default zero-dependency embedding provider used when semantic embedding models
    are not installed or vector features are disabled. Guarantees that the application
    functions without external network calls.
    """

    def __init__(self, dimension: int = settings.EMBEDDING_DIMENSION):
        self._dim = dimension

    async def embed_query(self, text: str) -> List[float]:
        return []

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[] for _ in texts]

    @property
    def dimension(self) -> int:
        return self._dim


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """Generates embeddings using a local Ollama instance (e.g. nomic-embed-text)."""

    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        model: str = settings.OLLAMA_EMBED_MODEL,
        dimension: int = settings.EMBEDDING_DIMENSION,
        timeout_seconds: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dim = dimension
        self.timeout = timeout_seconds

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_query(self, text: str) -> List[float]:
        vectors = await self.embed_documents([text])
        return vectors[0] if vectors else []

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Invokes Ollama embedding API asynchronously.
        Degrades gracefully if Ollama is unreachable.
        """
        if not texts:
            return []

        url = f"{self.base_url}/api/embed"
        payload = {"model": self.model, "input": texts}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    embeddings = data.get("embeddings") or []
                    if embeddings:
                        return embeddings
        except Exception as e:
            logger.debug(f"Ollama embedding service not reachable ({e}); falling back to zero vectors")

        return [[0.0] * self._dim for _ in texts]


def get_embedding_provider(provider_type: Optional[str] = None) -> BaseEmbeddingProvider:
    """
    Factory creating configured embedding provider.
    Defaults to OllamaEmbeddingProvider when configured, otherwise NullEmbeddingProvider.
    """
    selected = provider_type or getattr(settings, "EMBEDDING_PROVIDER", "ollama")
    if selected.lower() == "ollama":
        return OllamaEmbeddingProvider()
    return NullEmbeddingProvider()

