import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from backend.app.agent.providers.base import (
    BaseLLMProvider,
    ChatMessageInput,
    CompletionResult,
    StreamDelta,
)
from backend.app.core.config import settings
from backend.app.core.exceptions import ProviderUnavailableError
from backend.app.core.logging import logger


class OllamaProvider(BaseLLMProvider):
    """
    Local LLM Provider Adapter for Ollama HTTP daemon.
    Tuned for local qwen2.5:1.5b inference on an 8 GB RAM Windows workstation.
    Communicates via Ollama's HTTP API (/api/chat) without loading model weights into Python memory.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout if timeout is not None else settings.OLLAMA_REQUEST_TIMEOUT

    async def generate(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.OLLAMA_TEMPERATURE,
        max_tokens: int = settings.OLLAMA_NUM_PREDICT,
    ) -> CompletionResult:
        """
        Executes a non-streaming chat completion via Ollama POST /api/chat.
        Catches connection and timeout errors, converting them to ProviderUnavailableError.
        """
        endpoint = f"{self.base_url}/api/chat"
        formatted_messages = []
        if system:
            formatted_messages.append({"role": "system", "content": system})
        formatted_messages.extend([{"role": m.role, "content": m.content} for m in messages])

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            logger.error("Failed to connect to Ollama at %s: %s", self.base_url, exc)
            raise ProviderUnavailableError(
                provider="ollama",
                message=f"Cannot connect to local Ollama daemon at {self.base_url}. Verify Ollama is running.",
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error("Ollama request timed out after %ds at %s", self.timeout, endpoint)
            raise ProviderUnavailableError(
                provider="ollama",
                message=f"Ollama local model '{self.model}' timed out after {self.timeout} seconds.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama returned HTTP error %d: %s", exc.response.status_code, exc.response.text)
            raise ProviderUnavailableError(
                provider="ollama",
                message=f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error during Ollama generation: %s", exc)
            raise ProviderUnavailableError(
                provider="ollama",
                message=f"Unexpected error communicating with local Ollama: {str(exc)}",
            ) from exc

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        content = data.get("message", {}).get("content", "").strip()
        total_tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)

        return CompletionResult(
            content=content,
            total_tokens=total_tokens,
            model_name=self.model,
            finish_reason="completed" if data.get("done") else "truncated",
            latency_ms=elapsed_ms,
        )

    async def generate_stream(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.OLLAMA_TEMPERATURE,
        max_tokens: int = settings.OLLAMA_NUM_PREDICT,
    ) -> AsyncGenerator[StreamDelta, None]:
        """
        Streams chat completion tokens from Ollama via Server-Sent / NDJSON stream.
        """
        endpoint = f"{self.base_url}/api/chat"
        formatted_messages = []
        if system:
            formatted_messages.append({"role": "system", "content": system})
        formatted_messages.extend([{"role": m.role, "content": m.content} for m in messages])

        payload = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                async with client.stream("POST", endpoint, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            delta_text = chunk.get("message", {}).get("content", "")
                            is_done = chunk.get("done", False)
                            yield StreamDelta(
                                delta_text=delta_text,
                                is_complete=is_done,
                                finish_reason="completed" if is_done else None,
                            )
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                provider="ollama",
                message=f"Cannot connect to local Ollama daemon at {self.base_url}.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                provider="ollama",
                message=f"Ollama stream timed out after {self.timeout} seconds.",
            ) from exc
        except Exception as exc:
            raise ProviderUnavailableError(
                provider="ollama",
                message=f"Ollama streaming failure: {str(exc)}",
            ) from exc

    async def check_health(self) -> Dict[str, Any]:
        """
        Verifies Ollama connectivity and installed models without running model inference.
        """
        endpoint = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(endpoint)
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    is_model_installed = any(self.model in m for m in models)
                    return {
                        "healthy": True,
                        "status": "online",
                        "base_url": self.base_url,
                        "configured_model": self.model,
                        "model_installed": is_model_installed,
                        "available_models": models,
                        "message": f"Local Ollama online. Model '{self.model}' {'installed' if is_model_installed else 'not found'}.",
                    }
                return {
                    "healthy": False,
                    "status": "degraded",
                    "http_status": res.status_code,
                    "message": f"Ollama returned HTTP status {res.status_code}.",
                }
        except Exception as exc:
            return {
                "healthy": False,
                "status": "offline",
                "base_url": self.base_url,
                "configured_model": self.model,
                "error": str(exc),
                "message": f"Cannot connect to local Ollama daemon at {self.base_url}: {str(exc)}",
            }
