"""
Google Gemini Cloud LLM Provider Adapter.
Implements the official Google Gemini REST API (generateContent and streamGenerateContent)
using httpx without external SDK dependencies.
Configured by default for gemini-3.5-flash-lite (Google AI Studio free-tier eligible).
"""

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


class GeminiProvider(BaseLLMProvider):
    """
    Cloud LLM Provider Adapter for Google Gemini.
    - Default cloud provider for the Local LLM / Cloud LLM toggle.
    - Uses official REST API endpoint: https://generativelanguage.googleapis.com/v1beta
    - Authenticates via 'x-goog-api-key' header (never logs or leaks credentials).
    - Supports multi-turn dialogue with 'user' and 'model' roles.
    - Encapsulates system instructions inside 'system_instruction'.
    - Compatible with Gemini 3.5 Flash-Lite (omits deprecated temperature, topP, topK, and candidateCount).
    - Ensures the final conversation turn is a valid user message.
    - Distinguishes unconfigured (missing key), configured_unverified, and verified states.
    - Translates 400/401/403/429/timeouts into clear ProviderUnavailableError.
    - Never invokes remote cloud services during startup or unauthenticated health checks.
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    # Track verified status across the application lifespan
    _has_verified_call: bool = False

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = 60.0,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else 60.0

    @property
    def is_configured(self) -> bool:
        """Returns True if GEMINI_API_KEY is present and non-empty."""
        return bool(self.api_key and self.api_key.strip())

    @classmethod
    def mark_verified(cls) -> None:
        """Marks the provider as verified following a successful authorized call."""
        cls._has_verified_call = True

    @classmethod
    def is_verified(cls) -> bool:
        """Returns True if a live user-authorized call has succeeded."""
        return cls._has_verified_call

    def _sanitize(self, text: str) -> str:
        """Safeguards against leaking API credentials in log and exception messages."""
        if self.api_key and self.api_key in text:
            return text.replace(self.api_key, "[REDACTED_GEMINI_KEY]")
        return text

    def _format_payload(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.GEMINI_TEMPERATURE,
        max_tokens: int = settings.GEMINI_MAX_TOKENS,
    ) -> Dict[str, Any]:
        """
        Formats chat dialogue into Google Gemini generateContent request schema.
        Maps 'assistant' -> 'model', 'user' -> 'user', and merges system messages into system_instruction.
        Ensures alternating turn sequence starting with user and ending with a user turn.
        For Gemini 3.5 Flash-Lite, omits deprecated sampling parameters (temperature, topP, topK, candidateCount).
        """
        system_prompts: List[str] = []
        if system and system.strip():
            system_prompts.append(system.strip())

        dialogue_contents: List[Dict[str, Any]] = []

        for m in messages:
            if m.role == "system":
                if m.content.strip():
                    system_prompts.append(m.content.strip())
            elif m.role in ("user", "assistant"):
                role_name = "model" if m.role == "assistant" else "user"
                # If consecutive turns share the same role, combine parts
                if dialogue_contents and dialogue_contents[-1]["role"] == role_name:
                    dialogue_contents[-1]["parts"].append({"text": m.content})
                else:
                    dialogue_contents.append({
                        "role": role_name,
                        "parts": [{"text": m.content}],
                    })

        # 1. Gemini requires contents to start with role 'user'
        if not dialogue_contents:
            dialogue_contents = [{"role": "user", "parts": [{"text": "Hello"}]}]
        elif dialogue_contents[0]["role"] != "user":
            dialogue_contents.insert(0, {"role": "user", "parts": [{"text": "Hello"}]})

        # 2. Ensure final conversation turn is a valid user message for generateContent
        if dialogue_contents[-1]["role"] != "user":
            dialogue_contents.append({"role": "user", "parts": [{"text": "Please continue."}]})

        # 3. Request compatibility: Gemini 3.5 Flash-Lite (and 3.x models) omits
        # deprecated sampling parameters (temperature, topP, topK) and candidateCount.
        generation_config: Dict[str, Any] = {
            "maxOutputTokens": max_tokens,
        }
        is_gemini_3 = any(ver in self.model.lower() for ver in ("3.5", "3.6", "gemini-3", "flash-lite"))
        if not is_gemini_3 and temperature is not None:
            generation_config["temperature"] = temperature

        payload: Dict[str, Any] = {
            "contents": dialogue_contents,
            "generationConfig": generation_config,
        }

        if system_prompts:
            combined_system = "\n\n".join(system_prompts)
            payload["system_instruction"] = {
                "parts": [{"text": combined_system}]
            }

        return payload

    async def generate(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.GEMINI_TEMPERATURE,
        max_tokens: int = settings.GEMINI_MAX_TOKENS,
    ) -> CompletionResult:
        """
        Executes a non-streaming completion via Google Gemini REST API.
        """
        if not self.api_key or not self.api_key.strip():
            raise ProviderUnavailableError(
                provider="cloud",
                message=(
                    "GEMINI_API_KEY is not configured in the environment. "
                    "Set GEMINI_API_KEY to enable Cloud LLM, or switch to local Ollama mode."
                ),
            )

        endpoint = f"{self.base_url}/models/{self.model}:generateContent"
        payload = self._format_payload(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key.strip(),
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as exc:
            logger.error("Failed to connect to Google Gemini API: %s", self._sanitize(str(exc)))
            raise ProviderUnavailableError(
                provider="cloud",
                message="Cannot connect to Google Gemini API. Please check your network connection.",
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error("Gemini API request timed out after %.1fs", self.timeout)
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Gemini API request timed out after {int(self.timeout)} seconds.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            safe_detail = self._extract_error_detail(exc.response)
            logger.error("Gemini API returned HTTP %d: %s", status_code, safe_detail)

            if status_code in (401, 403):
                raise ProviderUnavailableError(
                    provider="cloud",
                    message="Gemini authentication failed (HTTP 401/403). Verify that your GEMINI_API_KEY is valid.",
                ) from exc
            elif status_code == 429:
                raise ProviderUnavailableError(
                    provider="cloud",
                    message=(
                        "Gemini API quota or rate limit exceeded (HTTP 429). "
                        "Free-tier quotas may be exhausted or throttled. Please retry shortly."
                    ),
                ) from exc
            elif status_code == 400:
                raise ProviderUnavailableError(
                    provider="cloud",
                    message=f"Gemini API request error (HTTP 400): {safe_detail}",
                ) from exc
            elif status_code >= 500:
                raise ProviderUnavailableError(
                    provider="cloud",
                    message=f"Google Gemini service unavailable (HTTP {status_code}). Please retry later.",
                ) from exc
            else:
                raise ProviderUnavailableError(
                    provider="cloud",
                    message=f"Gemini API returned HTTP {status_code}: {safe_detail}",
                ) from exc
        except Exception as exc:
            if isinstance(exc, ProviderUnavailableError):
                raise
            logger.exception("Unexpected error during Gemini generation: %s", self._sanitize(str(exc)))
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Unexpected error communicating with Gemini API: {self._sanitize(str(exc))}",
            ) from exc

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Parse candidates
        candidates = data.get("candidates", [])
        if not candidates:
            feedback = data.get("promptFeedback", {})
            block_reason = feedback.get("blockReason")
            if block_reason:
                raise ProviderUnavailableError(
                    provider="cloud",
                    message=f"Gemini generation blocked by safety filters: {block_reason}",
                )
            raise ProviderUnavailableError(
                provider="cloud",
                message="Gemini API returned an empty response with no candidate completions.",
            )

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "STOP")
        if finish_reason == "SAFETY":
            raise ProviderUnavailableError(
                provider="cloud",
                message="Gemini candidate was blocked by safety filters (finishReason: SAFETY).",
            )

        parts = candidate.get("content", {}).get("parts", [])
        text_content = "".join([p.get("text", "") for p in parts if "text" in p]).strip()

        # Token usage
        usage_metadata = data.get("usageMetadata", {})
        total_tokens = usage_metadata.get("totalTokenCount", 0)
        if not total_tokens:
            total_tokens = usage_metadata.get("promptTokenCount", 0) + usage_metadata.get("candidatesTokenCount", 0)

        # Mark as verified following successful completion
        self.mark_verified()

        return CompletionResult(
            content=text_content,
            total_tokens=total_tokens,
            model_name=self.model,
            finish_reason=finish_reason,
            latency_ms=elapsed_ms,
        )

    async def generate_stream(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.GEMINI_TEMPERATURE,
        max_tokens: int = settings.GEMINI_MAX_TOKENS,
    ) -> AsyncGenerator[StreamDelta, None]:
        """
        Streams completion tokens from Google Gemini via streamGenerateContent?alt=sse.
        """
        if not self.api_key or not self.api_key.strip():
            raise ProviderUnavailableError(
                provider="cloud",
                message="GEMINI_API_KEY is not configured in the environment.",
            )

        endpoint = f"{self.base_url}/models/{self.model}:streamGenerateContent?alt=sse"
        payload = self._format_payload(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key.strip(),
        }

        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        json_str = line[6:].strip()
                        if not json_str:
                            continue
                        try:
                            chunk = json.loads(json_str)
                            candidates = chunk.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    if "text" in p:
                                        yield StreamDelta(delta_text=p["text"], is_complete=False)
                        except json.JSONDecodeError:
                            continue

            self.mark_verified()
            yield StreamDelta(delta_text="", is_complete=True, finish_reason="completed")
        except httpx.HTTPStatusError as exc:
            safe_detail = self._extract_error_detail(exc.response)
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Gemini streaming error (HTTP {exc.response.status_code}): {safe_detail}",
            ) from exc
        except Exception as exc:
            if isinstance(exc, ProviderUnavailableError):
                raise
            raise ProviderUnavailableError(
                provider="cloud",
                message=f"Gemini streaming failure: {self._sanitize(str(exc))}",
            ) from exc

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Safely extracts error message from Gemini API response JSON without leaking secrets."""
        try:
            body = response.json()
            if isinstance(body, dict) and "error" in body:
                err = body["error"]
                msg = err.get("message") or err.get("status") or str(err)
                return self._sanitize(str(msg))
            return self._sanitize(response.text[:200])
        except Exception:
            return self._sanitize(response.text[:200]) if response.text else "Unknown error"

    async def check_health(self) -> Dict[str, Any]:
        """
        Validates Gemini provider status:
        - Key absent -> status: 'unconfigured'
        - Key present but not yet verified -> status: 'configured_unverified'
        - Successfully verified in real live call -> status: 'verified'
        Does NOT invoke remote cloud APIs during startup or health check.
        """
        has_key = bool(self.api_key and self.api_key.strip())
        if not has_key:
            return {
                "healthy": False,
                "status": "unconfigured",
                "configured": False,
                "verified": False,
                "provider": "gemini",
                "model": self.model,
                "free_tier_eligible": True,
                "message": "GEMINI_API_KEY is not configured. Cloud LLM is inactive; local Ollama is active.",
            }

        if self.is_verified():
            return {
                "healthy": True,
                "status": "verified",
                "configured": True,
                "verified": True,
                "provider": "gemini",
                "model": self.model,
                "free_tier_eligible": True,
                "message": f"Gemini Cloud LLM verified and operational with model '{self.model}'.",
            }

        return {
            "healthy": True,
            "status": "configured_unverified",
            "configured": True,
            "verified": False,
            "provider": "gemini",
            "model": self.model,
            "free_tier_eligible": True,
            "message": (
                f"GEMINI_API_KEY configured for model '{self.model}'. "
                "Key is present but unverified until first authorized live request."
            ),
        }
