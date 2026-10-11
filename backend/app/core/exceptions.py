"""
Custom application exception hierarchy for structured error handling.
"""

from typing import Any, Dict, Optional


class AppException(Exception):
    """Base class for all domain-specific application exceptions."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class DatabaseError(AppException):
    """Raised when database queries or connection pools fail."""

    def __init__(self, message: str = "Database connection or query failure", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=503, details=details)


class ProviderUnavailableError(AppException):
    """Raised when an LLM provider (Ollama, Gemini, Anthropic, or Pi Agent) is unreachable or fails."""

    def __init__(
        self,
        provider: str = "llm",
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 502,
    ):
        # Support positional signature where first argument is the error message
        if provider not in ("ollama", "cloud", "gemini", "anthropic", "pi_agent") and message is None:
            msg = provider
            prov = "llm"
        else:
            prov = provider
            msg = message or f"LLM Provider '{prov}' is currently unavailable or returned an error."

        super().__init__(message=msg, status_code=status_code, details=details)
        self.provider = prov
        self.detail = msg


class RAGRetrievalError(AppException):
    """Raised when transcript vector retrieval or embedding generation fails."""

    def __init__(self, message: str = "Failed to retrieve transcript context", details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=500, details=details)


class SessionNotFoundError(AppException):
    """Raised when a requested chat session does not exist."""

    def __init__(self, session_id: str):
        super().__init__(
            message=f"Chat session '{session_id}' not found.",
            status_code=404,
            details={"session_id": session_id},
        )


class IncompleteArtifactError(AppException):
    """Raised when an AI model generates truncated or structurally incomplete artifact content."""

    def __init__(
        self,
        message: str = "The AI model generated an incomplete artifact (output was truncated).",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, status_code=422, details=details)

