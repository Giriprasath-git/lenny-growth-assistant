"""
Pi Coding Agent SDK Provider Adapter.
Integrates with the isolated Node.js/TypeScript Pi Coding Agent bridge service (@earendil-works/pi-coding-agent)
communicating over local loopback at http://127.0.0.1:8765.

Connects to local Ollama (qwen2.5:1.5b) via OpenAI-compatible endpoint.
Preserves PostgreSQL as authoritative storage and enforces strict read-only tool restrictions (tools: []).
"""

from datetime import datetime, timezone
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx

from backend.app.agent.providers.base import BaseLLMProvider, ChatMessageInput, CompletionResult, StreamDelta
from backend.app.core.config import settings
from backend.app.core.exceptions import ProviderUnavailableError
from backend.app.core.logging import logger


class PiAgentProvider(BaseLLMProvider):
    """
    Adapter bridging FastAPI to the local Pi Coding Agent SDK service daemon.
    Supports local Ollama qwen2.5:1.5b execution, ephemeral in-memory sessions,
    and strict read-only execution boundaries.
    """

    framework: str = "pi_coding_agent"
    _has_verified_call: bool = False

    def __init__(
        self,
        service_url: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        url = service_url or base_url or settings.PI_AGENT_SERVICE_URL
        self.service_url = url.rstrip("/")
        self.base_url = self.service_url
        self.model = model or settings.PI_AGENT_MODEL
        self.timeout = float(timeout or settings.PI_AGENT_TIMEOUT)
        self.framework = "pi_coding_agent"

    @staticmethod
    def _sanitize_error_message(raw_message: str) -> str:
        """
        Strips sensitive authorization keys, cloud credentials, and internal filesystem paths
        from upstream error messages before propagating them to clients.
        """
        text = str(raw_message).strip()

        # Redact Bearer / API keys
        text = re.sub(r"(Bearer\s+)[a-zA-Z0-9_\-\.]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
        text = re.sub(r"(key[=:]\s*)[a-zA-Z0-9_\-\.]+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
        text = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_API_KEY]", text)
        text = re.sub(r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]", text)

        # Truncate at stack trace markers to prevent exposing internal code structures
        for marker in ("\n    at ", "\nTraceback (most recent call last):", "    at Object."):
            if marker in text:
                text = text.split(marker)[0].strip()

        return text

    @classmethod
    def mark_verified(cls) -> None:
        """Marks the Pi Agent SDK bridge as confirmed operational following a successful live call."""
        cls._has_verified_call = True

    @classmethod
    def is_verified(cls) -> bool:
        """Returns True if a live Pi SDK call has succeeded in the current process lifecycle."""
        return cls._has_verified_call

    async def check_health(self) -> Dict[str, Any]:
        """
        Polls the local Pi Coding Agent SDK service /health probe.
        Reports operational states:
        - 'stopped': Service daemon is not running on 127.0.0.1:8765
        - 'unconfigured': Daemon is running but @earendil-works/pi-coding-agent is not installed
        - 'online': Daemon and SDK are operational and connected to Ollama
        - 'verified': Live model inference has succeeded in the current process lifecycle
        """
        endpoint = f"{self.service_url}/health"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(endpoint)
                if res.status_code == 200:
                    data = res.json()
                    status_val = data.get("status", "")
                    is_ready = status_val in ("ready", "ok", "online") or bool(data.get("sdk_installed", False))
                    has_verified = self.is_verified()

                    if has_verified:
                        effective_status = "verified"
                    elif is_ready:
                        effective_status = "online"
                    else:
                        effective_status = "unconfigured"

                    package_name = data.get("package") or data.get("sdk_package", "@earendil-works/pi-coding-agent")
                    tools_enabled = data.get("tools_enabled", [])
                    tools_count = data.get("tools_count", len(tools_enabled))

                    return {
                        "healthy": is_ready,
                        "status": effective_status,
                        "configured": True,
                        "verified": has_verified,
                        "provider": "pi_agent",
                        "framework": "pi_coding_agent",
                        "service_url": self.service_url,
                        "base_url": self.service_url,
                        "model": data.get("target_model") or data.get("model", self.model),
                        "ollama_endpoint": data.get("ollama_endpoint", "http://127.0.0.1:11434/v1"),
                        "sdk_installed": data.get("sdk_installed", is_ready),
                        "package": package_name,
                        "sdk_package": package_name,
                        "tools_count": tools_count,
                        "tools_enabled": tools_enabled,
                        "message": (
                            "Pi Coding Agent SDK runtime is operational and verified by live inference."
                            if has_verified
                            else (
                                "Pi Coding Agent SDK service is running and ready."
                                if is_ready
                                else "Pi Coding Agent service is running, but SDK package requires 'npm install'."
                            )
                        ),
                    }
                else:
                    return {
                        "healthy": False,
                        "status": "error",
                        "configured": True,
                        "verified": False,
                        "provider": "pi_agent",
                        "framework": "pi_coding_agent",
                        "service_url": self.service_url,
                        "base_url": self.service_url,
                        "error": f"HTTP {res.status_code}: {res.text}",
                        "message": f"Pi Coding Agent service returned HTTP {res.status_code}",
                    }
        except httpx.ConnectError as exc:
            return {
                "healthy": False,
                "status": "stopped",
                "configured": True,
                "verified": False,
                "provider": "pi_agent",
                "framework": "pi_coding_agent",
                "service_url": self.service_url,
                "base_url": self.service_url,
                "error": f"Connection refused to {self.service_url}: {str(exc)}",
                "message": (
                    f"Pi Coding Agent SDK service is not running on {self.service_url}. "
                    "Start it via: 'cd pi-agent-service && npm start'. Ordinary local chat remains active."
                ),
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": "unavailable",
                "configured": True,
                "verified": False,
                "provider": "pi_agent",
                "framework": "pi_coding_agent",
                "service_url": self.service_url,
                "base_url": self.service_url,
                "error": str(e),
                "message": f"Failed to probe Pi Coding Agent service: {str(e)}",
            }

    async def generate(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.OLLAMA_TEMPERATURE,
        max_tokens: int = settings.OLLAMA_NUM_PREDICT,
    ) -> CompletionResult:
        """
        Submits prompt and multi-turn context to the Pi Coding Agent SDK bridge service.
        """
        endpoint = f"{self.service_url}/agent/prompt"

        # The active user prompt is the final message
        prompt_content = messages[-1].content if messages else ""

        payload = {
            "prompt": prompt_content,
            "system": system or "",
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "model": self.model,
            "maxTokens": max_tokens,
            "temperature": temperature,
        }

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                res = await client.post(endpoint, json=payload)
                if res.status_code >= 400:
                    try:
                        err_data = res.json()
                    except Exception:
                        err_data = {}

                    if res.status_code == 503 or ("not installed" in str(err_data).lower()):
                        raise ProviderUnavailableError(
                            provider="pi_agent",
                            message=(
                                "Pi Coding Agent SDK package is not installed. "
                                "Please run: 'cd pi-agent-service && npm install' and restart the service."
                            ),
                            status_code=503,
                        )

                    # Extract upstream diagnostic message safely
                    raw_err = ""
                    if isinstance(err_data, dict):
                        if isinstance(err_data.get("error"), str) and err_data["error"]:
                            raw_err = err_data["error"]
                        elif err_data.get("message"):
                            raw_err = str(err_data["message"])
                        elif err_data.get("details"):
                            raw_err = str(err_data["details"])

                    if not raw_err:
                        raw_err = res.text.strip() if res.text else f"Upstream error HTTP {res.status_code}"

                    sanitized_err = self._sanitize_error_message(raw_err)
                    map_status = 504 if res.status_code == 504 else 502
                    logger.error("Pi Coding Agent service returned HTTP %s: %s", res.status_code, sanitized_err)
                    raise ProviderUnavailableError(
                        provider="pi_agent",
                        message=f"Pi Coding Agent service execution failed: {sanitized_err}",
                        status_code=map_status,
                    )

                data = res.json()
        except (httpx.ConnectError, httpx.NetworkError) as err:
            logger.error("Failed to connect to Pi Coding Agent SDK service at %s: %s", endpoint, str(err))
            raise ProviderUnavailableError(
                provider="pi_agent",
                message=(
                    f"Pi Coding Agent SDK service is not reachable on {self.service_url}. "
                    "Ensure the bridge service is running ('cd pi-agent-service && npm start') "
                    "or switch to provider='ollama' for direct local execution."
                ),
                status_code=502,
            ) from err
        except httpx.TimeoutException as err:
            logger.error("Pi Coding Agent SDK execution timed out after %s seconds", self.timeout)
            raise ProviderUnavailableError(
                provider="pi_agent",
                message=f"Pi Coding Agent SDK execution timed out after {self.timeout} seconds.",
                status_code=504,
            ) from err
        except httpx.HTTPStatusError as err:
            raw_err = ""
            if err.response is not None:
                try:
                    err_json = err.response.json()
                    if isinstance(err_json, dict):
                        if isinstance(err_json.get("error"), str) and err_json["error"]:
                            raw_err = err_json["error"]
                        elif err_json.get("message"):
                            raw_err = str(err_json["message"])
                        elif err_json.get("details"):
                            raw_err = str(err_json["details"])
                except Exception:
                    pass
                if not raw_err:
                    raw_err = err.response.text.strip() if err.response.text else f"Upstream error HTTP {err.response.status_code}"
            if not raw_err:
                raw_err = str(err)

            sanitized_err = self._sanitize_error_message(raw_err)
            logger.error("Pi Coding Agent service returned HTTP %s: %s", err.response.status_code if err.response else "error", sanitized_err)
            map_status = 504 if (err.response and err.response.status_code == 504) else 502
            raise ProviderUnavailableError(
                provider="pi_agent",
                message=f"Pi Coding Agent service execution failed: {sanitized_err}",
                status_code=map_status,
            ) from err

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        content = data.get("content", "").strip()

        if not content:
            raise ProviderUnavailableError(
                provider="pi_agent",
                message="Pi Coding Agent SDK returned empty generation output.",
                status_code=502,
            )

        self.mark_verified()

        usage_data = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        total_tokens = (
            usage_data.get("total_tokens")
            or data.get("total_tokens")
            or max(1, len(content) // 4)
        )

        return CompletionResult(
            content=content,
            total_tokens=int(total_tokens),
            model_name=data.get("model", self.model),
            finish_reason="completed",
            latency_ms=data.get("latency_ms", latency_ms),
            raw_response=data,
        )

    async def generate_stream(
        self,
        messages: List[ChatMessageInput],
        system: Optional[str] = None,
        temperature: float = settings.OLLAMA_TEMPERATURE,
        max_tokens: int = settings.OLLAMA_NUM_PREDICT,
    ) -> AsyncGenerator[StreamDelta, None]:
        """Streaming generator yielding agent output deltas."""
        result = await self.generate(
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield StreamDelta(delta_text=result.content, is_complete=True, finish_reason="completed")
