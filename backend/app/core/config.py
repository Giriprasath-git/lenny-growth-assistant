"""
Application configuration management using Pydantic Settings.
Loads environment variables from .env file or system environment with strict validation.
"""

from pathlib import Path
from typing import List, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine absolute project root dynamically (4 levels up from backend/app/core/config.py)
# backend/app/core/config.py -> core (parents[0]) -> app (parents[1]) -> backend (parents[2]) -> project root (parents[3])
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
ENV_FILE_PATH: Path = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --------------------------------------------------------------------------
    # Application Info & Server
    # --------------------------------------------------------------------------
    APP_NAME: str = Field(default="Lenny Growth Assistant", description="Application name")
    APP_VERSION: str = Field(default="0.1.0", description="Application version")
    ENVIRONMENT: Literal["development", "staging", "production"] = Field(
        default="development", description="Runtime environment"
    )
    DEBUG: bool = Field(default=True, description="Debug mode flag")
    LOG_LEVEL: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR")
    HOST: str = Field(default="127.0.0.1", description="FastAPI bind host")
    PORT: int = Field(default=8000, description="FastAPI bind port")
    ALLOWED_CORS_ORIGINS: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated list of allowed CORS origins",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_CORS_ORIGINS.split(",") if origin.strip()]

    # --------------------------------------------------------------------------
    # PostgreSQL Database & Persistence
    # --------------------------------------------------------------------------
    POSTGRES_HOST: str = Field(default="127.0.0.1", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_DB: str = Field(default="lenny_growth_db", description="Database name")
    POSTGRES_USER: str = Field(default="postgres", description="Database user")
    POSTGRES_PASSWORD: str = Field(default="postgres", description="Database password")
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/lenny_growth_db",
        description="SQLAlchemy asyncpg connection URL",
    )
    # Database Pool Settings (Tuned for 8 GB RAM host)
    DB_POOL_SIZE: int = Field(default=5, description="Async connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=5, description="Max overflow connections")
    DB_POOL_TIMEOUT: float = Field(default=30.0, description="Pool checkout timeout in seconds")
    DB_POOL_RECYCLE: int = Field(default=1800, description="Connection recycle interval in seconds")
    DB_ECHO: bool = Field(default=False, description="Echo SQL queries to logs")

    @property
    def masked_database_url(self) -> str:
        """Returns DATABASE_URL with password masked for safe logging."""
        url = self.DATABASE_URL
        if "@" in url and "://" in url:
            scheme_user = url.split("@")[0]
            host_db = url.split("@")[1]
            if ":" in scheme_user:
                scheme_user_parts = scheme_user.split(":")
                # scheme_user_parts[0] is postgresql+asyncpg, parts[1] is //username, parts[2] is password
                if len(scheme_user_parts) >= 3:
                    masked_scheme_user = f"{scheme_user_parts[0]}:{scheme_user_parts[1]}:***"
                    return f"{masked_scheme_user}@{host_db}"
        return url

    # --------------------------------------------------------------------------
    # LLM Providers Configuration
    # --------------------------------------------------------------------------
    DEFAULT_LLM_PROVIDER: Literal["cloud", "ollama", "pi_agent"] = Field(
        default="ollama", description="Default active provider: 'ollama' (Local default), 'cloud' (Gemini cloud default), or 'pi_agent' (Pi Coding Agent SDK)"
    )

    # Cloud LLM Provider (Google Gemini - Documented Free-Tier Default)
    GEMINI_API_KEY: str = Field(default="", description="Google Gemini API key (Optional; required for Cloud LLM)")
    GEMINI_MODEL: str = Field(
        default="gemini-3.5-flash-lite",
        description="Configurable Gemini model identifier (default: gemini-3.5-flash-lite, Google's stable free-tier eligible text generation model). Availability must be verified in Google AI Studio.",
    )
    GEMINI_MAX_TOKENS: int = Field(default=2500, description="Max output tokens for Gemini generation")
    GEMINI_TEMPERATURE: float = Field(default=0.2, description="Sampling temperature for Gemini")

    # Agent Framework & Legacy Cloud LLM Settings (Anthropic)
    AGENT_FRAMEWORK: Literal["claude_agent_sdk", "pi_coding_agent"] = Field(
        default="pi_coding_agent",
        description="Active agent framework: 'pi_coding_agent' (Real Pi Coding Agent SDK) or 'claude_agent_sdk'",
    )
    ANTHROPIC_API_KEY: str = Field(default="", description="API Key for Legacy Cloud Agent / Anthropic (Optional)")
    ANTHROPIC_MODEL: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Configurable legacy cloud model identifier (e.g. claude-3-5-sonnet-20241022).",
    )
    ANTHROPIC_MAX_TOKENS: int = Field(default=4096, description="Max generation tokens")
    ANTHROPIC_TEMPERATURE: float = Field(default=0.2, description="Sampling temperature")

    # Pi Coding Agent SDK Service (Local isolated runtime bridge)
    PI_AGENT_SERVICE_URL: str = Field(
        default="http://127.0.0.1:8765",
        description="Base URL for the isolated Pi Coding Agent Node.js/TypeScript SDK service daemon",
    )
    PI_AGENT_TIMEOUT: float = Field(
        default=180.0,
        description="HTTP timeout in seconds for Pi Coding Agent SDK execution (tuned for 8 GB RAM CPU inference)",
    )
    PI_AGENT_MODEL: str = Field(
        default="qwen2.5:1.5b",
        description="Model identifier targeted by the Pi Coding Agent SDK via local Ollama endpoint",
    )
    PI_AGENT_ENABLED: bool = Field(
        default=True,
        description="Whether Pi Coding Agent SDK service integration is enabled in the backend",
    )

    # Local Ollama (Primary local development provider)
    OLLAMA_BASE_URL: str = Field(
        default="http://127.0.0.1:11434", description="Base URL for local Ollama daemon"
    )
    OLLAMA_MODEL: str = Field(
        default="qwen2.5:1.5b", description="Local model name downloaded and tested for 8 GB RAM machines"
    )
    OLLAMA_EMBED_MODEL: str = Field(
        default="nomic-embed-text", description="Local embedding model name"
    )
    OLLAMA_REQUEST_TIMEOUT: int = Field(
        default=180,
        description="Ollama HTTP timeout in seconds (tuned to 180s for slower CPU inference on 8 GB RAM)",
    )
    OLLAMA_NUM_PREDICT: int = Field(default=512, description="Max generated tokens for local inference on 8 GB RAM host")
    OLLAMA_TEMPERATURE: float = Field(default=0.2, description="Sampling temperature for local inference")

    # --------------------------------------------------------------------------
    # RAG & Transcript Retrieval
    # --------------------------------------------------------------------------
    EMBEDDING_PROVIDER: Literal["ollama", "cloud"] = Field(
        default="ollama", description="Embedding provider"
    )
    EMBEDDING_MODEL: str = Field(default="nomic-embed-text", description="Active embedding model")
    EMBEDDING_DIMENSION: int = Field(default=768, description="Vector embedding dimension")
    RAG_TOP_K: int = Field(default=5, description="Number of top chunks to retrieve")
    RAG_SIMILARITY_THRESHOLD: float = Field(
        default=0.65, description="Minimum cosine similarity cutoff"
    )
    TRANSCRIPT_CHUNK_SIZE: int = Field(
        default=500, description="Target chunk size in tokens/words"
    )
    TRANSCRIPT_CHUNK_OVERLAP: int = Field(
        default=100, description="Overlap tokens between sequential chunks"
    )

    # --------------------------------------------------------------------------
    # Resource Boundaries for 8 GB RAM Machine
    # --------------------------------------------------------------------------
    MAX_SYSTEM_RAM_USAGE_PERCENT: float = Field(
        default=85.0, description="Safeguard threshold before warning/throttling local inference"
    )


# Instantiate singleton settings object
settings = Settings()
