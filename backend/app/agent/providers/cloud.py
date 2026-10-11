import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from backend.app.agent.providers.base import (
    BaseLLMProvider,
    ChatMessageInput,
    CompletionResult,
    StreamDelta,
)
from backend.app.core.config import settings
from backend.app.core.exceptions import ProviderUnavailableError
from backend.app.core.logging import logger


class CloudAnthropicProvider(BaseLLMProvider):
    """
    Cloud LLM Provider Adapter for Anthropic Claude.
    Optional provider: FastAPI starts cleanly without ANTHROPIC_API_KEY.
    If invoked without an API key, raises ProviderUnavailableError without crashing the application.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.ANTHROPIC_API_KEY
        self.model = model if model is not None else settings.ANTHROPIC_MODEL

    @property
    def is_configured(self) -> bool:
        """Returns True if ANTHROPIC_API_KEY is present and non-empty."""
        return bool(self.api_key and self.api_key.strip())

    async def generate(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.ANTHROPIC_TEMPERATURE,
        max_tokens: int = settings.ANTHROPIC_MAX_TOKENS,
    ) -> CompletionResult:
        """
        Executes a completion via Anthropic Messages API.
        Extracts system messages to adhere to Anthropic's top-level system parameter requirement.
        """
        if not self.api_key:
            raise ProviderUnavailableError(
                provider="cloud",
                message="ANTHROPIC_API_KEY is not configured in the environment. Set the key or switch to local Ollama.",
            )

        try:
            import anthropic
        except ImportError as exc:
            raise ProviderUnavailableError(
                provider="cloud",
                message="The 'anthropic' package is not installed.",
            ) from exc

        # Separate system messages from user/assistant dialogue
        system_prompts = []
        if system:
            system_prompts.append(system)
        system_prompts.extend([m.content for m in messages if m.role == "system"])
        system_text = "\n\n".join(system_prompts) if system_prompts else ""
        dialogue_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        if not dialogue_messages:
            dialogue_messages = [{"role": "user", "content": "Hello"}]

        start_time = time.perf_counter()
        try:
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": dialogue_messages,
            }
            if system_text:
                kwargs["system"] = system_text

            response = await client.messages.create(**kwargs)
        except anthropic.APIConnectionError as exc:
            logger.error("Failed to connect to Anthropic API: %s", exc)
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Failed to connect to Anthropic Cloud API: {str(exc)}",
            ) from exc
        except anthropic.RateLimitError as exc:
            logger.error("Anthropic API rate limit exceeded: %s", exc)
            raise ProviderUnavailableError(
                provider="cloud",
                message="Anthropic API rate limit exceeded. Please retry shortly.",
            ) from exc
        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API status error %d: %s", exc.status_code, exc.message)
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Anthropic API returned error {exc.status_code}: {exc.message}",
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error during Anthropic API generation: %s", exc)
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Cloud generation failed: {str(exc)}",
            ) from exc

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        content_parts = [block.text for block in response.content if hasattr(block, "text")]
        combined_text = "".join(content_parts).strip()
        total_tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

        return CompletionResult(
            content=combined_text,
            total_tokens=total_tokens,
            model_name=self.model,
            finish_reason=response.stop_reason or "completed",
            latency_ms=elapsed_ms,
        )

    async def generate_stream(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.ANTHROPIC_TEMPERATURE,
        max_tokens: int = settings.ANTHROPIC_MAX_TOKENS,
    ) -> AsyncGenerator[StreamDelta, None]:
        """
        Streams completion tokens via Anthropic streaming API.
        """
        if not self.api_key:
            raise ProviderUnavailableError(
                provider="cloud",
                message="ANTHROPIC_API_KEY is not configured in the environment.",
            )

        try:
            import anthropic
        except ImportError as exc:
            raise ProviderUnavailableError(
                provider="cloud",
                message="The 'anthropic' package is not installed.",
            ) from exc

        system_prompts = []
        if system:
            system_prompts.append(system)
        system_prompts.extend([m.content for m in messages if m.role == "system"])
        system_text = "\n\n".join(system_prompts) if system_prompts else ""
        dialogue_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        if not dialogue_messages:
            dialogue_messages = [{"role": "user", "content": "Hello"}]

        try:
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": dialogue_messages,
            }
            if system_text:
                kwargs["system"] = system_text

            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield StreamDelta(delta_text=text, is_complete=False)
            yield StreamDelta(delta_text="", is_complete=True, finish_reason="completed")
        except Exception as exc:
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Anthropic streaming failed: {str(exc)}",
            ) from exc

    async def check_health(self) -> Dict[str, Any]:
        """
        Validates cloud configuration without contacting remote services at startup.
        """
        if not self.api_key:
            return {
                "healthy": False,
                "status": "unconfigured",
                "configured": False,
                "message": "ANTHROPIC_API_KEY is not configured. Running in local Ollama mode.",
            }
        return {
            "healthy": True,
            "status": "configured",
            "configured": True,
            "model": self.model,
            "message": f"Cloud Anthropic provider configured for model '{self.model}'.",
        }
