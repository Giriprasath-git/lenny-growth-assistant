"""
Automated Test Suite for Real Pi Coding Agent SDK Bridge Integration.
Phase 4C: Implement Real Pi Coding Agent SDK Integration.

Official SDK References:
- SDK: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md
- Models: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md

Covers:
- PiAgentProvider defaults and initialization against loopback bridge service
- Health check transitions (online vs stopped/offline)
- Successful generation contract with token usage and SDK metadata
- Graceful error handling for missing/stopped service (ConnectError -> HTTP 502)
- Provider timeouts (TimeoutException -> HTTP 504)
- Upstream service error mapping (HTTP 500 -> HTTP 502)
- GET /api/v1/chat/sdk-status reporting Pi SDK package, endpoint, and security policy
- POST /api/v1/chat/agent end-to-end execution with transcript citation persistence
- Verification that ordinary chat (Ollama direct) remains fully available if Pi service is stopped
- Multi-turn conversation continuity with PostgreSQL persistence
- Strict security verification: empty tools policy (tools: [], noTools: 'all', noExtensions: true)
- Manifest validation: models.json configures api: "openai-completions" and apiKey: "ollama"
- Package validation: pi-agent-service/package.json targets @earendil-works/pi-coding-agent

ALL EXTERNAL HTTP/MODEL CALLS ARE FULLY MOCKED. ZERO LIVE NETWORK CALLS.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.engine import AgentEngine
from backend.app.agent.providers.base import ChatMessageInput, CompletionResult
from backend.app.agent.providers.ollama import OllamaProvider
from backend.app.agent.providers.pi_agent import PiAgentProvider
from backend.app.core.config import settings
from backend.app.core.exceptions import ProviderUnavailableError
from backend.app.db.models.message import ChatMessage, MessageCitation
from backend.app.db.models.session import ChatSession
from backend.app.db.models.transcript import TranscriptChunk
from backend.app.rag.retriever import GroundedEvidence, TranscriptRetriever
from backend.app.schemas.chat import ChatTurnResponse

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
OFFICIAL_SDK_PACKAGE = "@earendil-works/pi-coding-agent"


# ==============================================================================
# 1. Manifest & Configuration Contract Tests
# ==============================================================================

def test_models_json_configuration_schema():
    """
    Verifies that pi-agent-service/models.json adheres to official Pi documentation:
    - uses api: 'openai-completions' (not 'openai')
    - sets apiKey: 'ollama' dummy key placeholder
    - registers qwen2.5:1.5b with local Ollama endpoint
    """
    models_file = WORKSPACE_ROOT / "pi-agent-service" / "models.json"
    assert models_file.is_file(), f"Missing models.json at {models_file}"

    with open(models_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "providers" in data
    assert "ollama" in data["providers"]
    ollama_cfg = data["providers"]["ollama"]

    assert ollama_cfg["api"] == "openai-completions", "API identifier must be 'openai-completions'"
    assert ollama_cfg["apiKey"] == "ollama", "Ollama requires 'apiKey': 'ollama' placeholder in Pi SDK"
    assert "11434/v1" in ollama_cfg["baseUrl"]

    model_ids = [m["id"] for m in ollama_cfg.get("models", [])]
    assert "qwen2.5:1.5b" in model_ids


def test_pi_agent_service_package_json_dependency():
    """Verifies that pi-agent-service/package.json declares exact published @earendil-works/pi-coding-agent 1.1.0 dependency."""
    pkg_file = WORKSPACE_ROOT / "pi-agent-service" / "package.json"
    assert pkg_file.is_file(), f"Missing package.json at {pkg_file}"

    with open(pkg_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    deps = data.get("dependencies", {})
    assert OFFICIAL_SDK_PACKAGE in deps, f"Expected {OFFICIAL_SDK_PACKAGE} in dependencies"
    assert deps[OFFICIAL_SDK_PACKAGE] == "1.1.0", (
        f"Expected exact published SDK version 1.1.0, found: {deps.get(OFFICIAL_SDK_PACKAGE)}"
    )


def test_pi_agent_service_model_runtime_contract():
    """
    Verifies that pi-agent-service/src/agent.ts conforms to SDK 1.1.0 ModelRuntime API:
    - uses ModelRuntime.create({ modelsPath })
    - resolves model via modelRuntime.getModel('ollama', targetModel)
    - configures createAgentSession with modelRuntime and strict security boundaries
    - extracts output via getLastAssistantText() and cleans up via dispose()
    """
    agent_src = WORKSPACE_ROOT / "pi-agent-service" / "src" / "agent.ts"
    assert agent_src.is_file(), f"Missing agent.ts at {agent_src}"

    code = agent_src.read_text(encoding="utf-8")
    assert "ModelRuntime" in code, "agent.ts must integrate ModelRuntime per SDK 1.1.0 specification"
    assert "modelsPath" in code, "agent.ts must configure ModelRuntime with modelsPath"
    assert "getModel" in code, "agent.ts must use modelRuntime.getModel() for provider lookup"
    assert "createAgentSession" in code, "agent.ts must call createAgentSession"
    assert "getLastAssistantText" in code, "agent.ts must extract completions via getLastAssistantText"
    assert "dispose" in code, "agent.ts must release sessions via session.dispose()"
    assert "noTools: \"all\"" in code, "agent.ts must enforce noTools: 'all' security policy"
    assert "noExtensions: true" in code, "agent.ts must enforce noExtensions: true security policy"



# ==============================================================================
# 2. Provider Adapter & Configuration Tests
# ==============================================================================

def test_pi_agent_provider_defaults():
    """Verifies that PiAgentProvider defaults to qwen2.5:1.5b and loopback bridge service."""
    provider = PiAgentProvider()
    assert provider.model == "qwen2.5:1.5b"
    assert provider.base_url == "http://127.0.0.1:8765"
    assert provider.timeout == 180.0
    assert provider.framework == "pi_coding_agent"


@pytest.mark.asyncio
async def test_pi_agent_health_check_online():
    """Verifies health check probe when the bridge microservice is online."""
    mock_payload = {
        "status": "ready",
        "service": "pi-agent-service",
        "framework": "pi_coding_agent",
        "package": OFFICIAL_SDK_PACKAGE,
        "model": "qwen2.5:1.5b",
        "ollama_endpoint": "http://127.0.0.1:11434/v1",
        "tools_count": 0,
        "sdk_installed": True,
    }

    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_payload

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        provider = PiAgentProvider()
        try:
            health = await provider.check_health()

            assert health["status"] == "online"
            assert health["configured"] is True
            # Do not report live inference as verified merely because the bridge is running
            assert health["verified"] is False
            assert health["package"] == OFFICIAL_SDK_PACKAGE
            assert health["tools_count"] == 0

            # Verify transition to verified state after live inference
            provider.mark_verified()
            verified_health = await provider.check_health()
            assert verified_health["verified"] is True
            assert verified_health["status"] == "verified"
        finally:
            PiAgentProvider._has_verified_call = False


@pytest.mark.asyncio
async def test_pi_agent_health_check_stopped():
    """Verifies health check probe when the bridge microservice is stopped."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection refused")):
        provider = PiAgentProvider()
        health = await provider.check_health()

        assert health["status"] == "stopped"
        assert health["configured"] is True
        assert health["verified"] is False
        assert "Connection refused" in health["error"]


# ==============================================================================
# 3. Invocation Contract & Error Handling Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_pi_agent_generate_success():
    """Verifies successful completion generation via the Pi SDK bridge service."""
    mock_payload = {
        "content": "Brian Chesky focused on high-touch retention loops early on [1].",
        "model": "qwen2.5:1.5b",
        "latency_ms": 350.2,
        "usage": {"total_tokens": 128},
        "metadata": {
            "framework": "pi_coding_agent",
            "package": OFFICIAL_SDK_PACKAGE,
            "session_mode": "in_memory",
            "tools_count": 0,
            "security_policy": "empty_tools_read_only",
        },
    }

    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_payload

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        provider = PiAgentProvider()
        result = await provider.generate(
            messages=[ChatMessageInput(role="user", content="How did Brian Chesky grow Airbnb?")],
            system="You are Lenny Growth Assistant.",
            max_tokens=512,
        )

        assert isinstance(result, CompletionResult)
        assert "Brian Chesky focused on high-touch retention loops" in result.content
        assert result.model_name == "qwen2.5:1.5b"
        assert result.total_tokens == 128
        assert result.latency_ms == 350.2
        assert result.raw_response["metadata"]["tools_count"] == 0


@pytest.mark.asyncio
async def test_pi_agent_generate_connection_failure():
    """Verifies ProviderUnavailableError (HTTP 502) is raised when the SDK service is unreachable."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection refused")):
        provider = PiAgentProvider()
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Test query")],
            )

        assert exc_info.value.status_code == 502
        assert "not reachable" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_pi_agent_generate_timeout():
    """Verifies ProviderUnavailableError (HTTP 504) is raised when the SDK invocation times out."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Read timed out")):
        provider = PiAgentProvider()
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Test query")],
            )

        assert exc_info.value.status_code == 504
        assert "timed out" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_pi_agent_generate_upstream_500():
    """Verifies ProviderUnavailableError (HTTP 502) is raised when the bridge returns an upstream error."""
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 500
    mock_response.json.return_value = {"error": "Ollama service unavailable at http://127.0.0.1:11434/v1"}
    mock_response.text = json.dumps({"error": "Ollama service unavailable"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        provider = PiAgentProvider()
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Test query")],
            )

        assert exc_info.value.status_code == 502
        assert "Ollama service unavailable" in str(exc_info.value.detail)


# ==============================================================================
# 4. Security Policy & SDK Status Tests
# ==============================================================================

def test_pi_agent_security_empty_tools_policy():
    """Verifies that PiCodingAgentAdapter enforces empty tools policy (tools: []) to prevent arbitrary code execution."""
    engine = AgentEngine()
    audit = engine.pi_sdk_boundary.get_audit_summary()

    assert audit["package"] == OFFICIAL_SDK_PACKAGE
    assert audit["tools_policy"] == "empty_tools_read_only"
    assert audit["service_url"] == "http://127.0.0.1:8765"
    assert audit["endpoint"] == "http://127.0.0.1:11434/v1"
    # Status remains unverified until manual user smoke test
    assert audit["status"] == "unverified"


@pytest.mark.asyncio
async def test_api_sdk_status_includes_pi_coding_agent(client: AsyncClient):
    """Verifies GET /api/v1/chat/sdk-status reports Pi Coding Agent SDK configuration and health."""
    mock_health = {
        "status": "online",
        "service": "pi-agent-service",
        "framework": "pi_coding_agent",
        "package": OFFICIAL_SDK_PACKAGE,
        "configured": True,
        "verified": True,
    }

    with patch.object(PiAgentProvider, "check_health", new_callable=AsyncMock, return_value=mock_health):
        res = await client.get("/api/v1/chat/sdk-status")
        assert res.status_code == 200
        data = res.json()

        sdks = data["coding_agent_sdks"]
        pi_sdk = sdks["pi_coding_agent"]
        assert pi_sdk["package"] == OFFICIAL_SDK_PACKAGE
        assert pi_sdk["tools_policy"] == "empty_tools_read_only"
        assert pi_sdk["service_health"]["status"] == "online"


# ==============================================================================
# 5. Application Integration & Persistence Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_api_chat_agent_endpoint_success(client: AsyncClient, test_db_session: AsyncSession):
    """
    Verifies POST /api/v1/chat/agent executes grounded turn via Pi SDK bridge,
    saves user/assistant messages in PostgreSQL, and persists podcast citations.
    """
    # 1. Create a session
    create_res = await client.post("/api/v1/sessions", json={"title": "Pi SDK Test", "provider": "pi_agent"})
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    # 2. Insert synthetic transcript chunk for RAG grounding
    chunk = TranscriptChunk(
        id=uuid.uuid4(),
        episode_id="ep-lenny-retention",
        episode_title="Building the Retention Flywheel",
        guest_name="Elena Verna",
        chunk_index=0,
        timestamp_start="05:12",
        timestamp_end="07:45",
        content="B2B PLG growth requires pairing freemium models with rapid activation loops.",
    )
    test_db_session.add(chunk)
    await test_db_session.commit()
    await test_db_session.refresh(chunk)

    mock_completion = CompletionResult(
        content="Elena Verna explains that B2B PLG growth depends on rapid activation loops [1].",
        total_tokens=140,
        model_name="qwen2.5:1.5b",
        latency_ms=210.0,
        raw_response={
            "metadata": {
                "framework": "pi_coding_agent",
                "package": OFFICIAL_SDK_PACKAGE,
                "tools_count": 0,
            }
        },
    )

    with patch.object(PiAgentProvider, "generate", new_callable=AsyncMock, return_value=mock_completion):
        res = await client.post(
            "/api/v1/chat/agent",
            json={
                "session_id": session_id,
                "message": "What is Elena Verna's view on B2B PLG growth?",
                "top_k": 2,
            },
        )

        assert res.status_code == 200
        data = res.json()

        assert data["session_id"] == session_id
        assert data["provider"] == "pi_agent"
        assert data["model"] == "qwen2.5:1.5b"
        assert data["framework"] == "pi_coding_agent"
        assert data["is_sdk"] is True
        assert "Elena Verna explains" in data["assistant_message"]["content"]
        assert len(data["citations"]) >= 1

        citation = data["citations"][0]
        assert citation["episode_id"] == "ep-lenny-retention"
        assert citation["guest_name"] == "Elena Verna"
        assert citation["timestamp_start"] == "05:12"

        # 3. Verify PostgreSQL message persistence
        msg_stmt = select(ChatMessage).where(ChatMessage.session_id == uuid.UUID(session_id))
        msg_result = await test_db_session.execute(msg_stmt)
        messages = list(msg_result.scalars().all())

        assert len(messages) == 2
        user_msg = next(m for m in messages if m.role == "user")
        assistant_msg = next(m for m in messages if m.role == "assistant")

        assert user_msg.content == "What is Elena Verna's view on B2B PLG growth?"
        assert "Elena Verna explains" in assistant_msg.content
        assert assistant_msg.provider_metadata["framework"] == "pi_coding_agent"
        assert assistant_msg.provider_metadata["is_sdk"] is True


@pytest.mark.asyncio
async def test_normal_chat_remains_available_when_sdk_service_stopped(
    client: AsyncClient, test_db_session: AsyncSession
):
    """
    Verifies that standard local chat via Ollama (provider='ollama') operates normally
    even when the Pi SDK service is stopped or unreachable.
    """
    create_res = await client.post("/api/v1/sessions", json={"title": "Ollama Standard Chat", "provider": "ollama"})
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    mock_completion = CompletionResult(
        content="Standard direct Ollama response without SDK.",
        total_tokens=90,
        model_name="qwen2.5:1.5b",
        latency_ms=150.0,
    )

    with patch.object(OllamaProvider, "generate", new_callable=AsyncMock, return_value=mock_completion):
        res = await client.post(
            "/api/v1/chat",
            json={
                "session_id": session_id,
                "message": "Standard chat question",
                "provider": "ollama",
            },
        )

        assert res.status_code == 200
        data = res.json()
        assert data["provider"] == "ollama"
        assert data["assistant_message"]["content"] == "Standard direct Ollama response without SDK."
        assert data["is_sdk"] is False


@pytest.mark.asyncio
async def test_api_chat_agent_service_stopped_returns_502(client: AsyncClient):
    """Verifies POST /api/v1/chat/agent returns HTTP 502 with clear diagnostic message when service is offline."""
    create_res = await client.post("/api/v1/sessions", json={"title": "Service Stopped Test", "provider": "pi_agent"})
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    with patch.object(
        PiAgentProvider,
        "generate",
        new_callable=AsyncMock,
        side_effect=ProviderUnavailableError(
            "Pi Coding Agent SDK bridge service (pi-agent-service) is not reachable at http://127.0.0.1:8765. "
            "Please ensure the service is running (cd pi-agent-service && npm run dev).",
            status_code=502,
        ),
    ):
        res = await client.post(
            "/api/v1/chat/agent",
            json={
                "session_id": session_id,
                "message": "Hello Agent",
            },
        )

        assert res.status_code == 502
        data = res.json()
        assert "not reachable" in data["detail"]
        assert "npm run dev" in data["detail"]


@pytest.mark.asyncio
async def test_multi_turn_history_continuity_with_pi_agent(
    client: AsyncClient, test_db_session: AsyncSession
):
    """Verifies multi-turn history continuity across consecutive turns using the Pi SDK bridge."""
    create_res = await client.post("/api/v1/sessions", json={"title": "Multi-turn Agent Test", "provider": "pi_agent"})
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    turn1_completion = CompletionResult(
        content="Answer turn 1.",
        total_tokens=50,
        model_name="qwen2.5:1.5b",
        latency_ms=100.0,
    )
    turn2_completion = CompletionResult(
        content="Answer turn 2 building on turn 1.",
        total_tokens=60,
        model_name="qwen2.5:1.5b",
        latency_ms=110.0,
    )

    with patch.object(PiAgentProvider, "generate", new_callable=AsyncMock, side_effect=[turn1_completion, turn2_completion]):
        # Turn 1
        res1 = await client.post(
            "/api/v1/chat/agent",
            json={"session_id": session_id, "message": "Turn 1 question"},
        )
        assert res1.status_code == 200

        # Turn 2
        res2 = await client.post(
            "/api/v1/chat/agent",
            json={"session_id": session_id, "message": "Turn 2 question"},
        )
        assert res2.status_code == 200

        # Verify DB has 4 messages total (user1, asst1, user2, asst2)
        msg_stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == uuid.UUID(session_id))
            .order_by(ChatMessage.created_at.asc())
        )
        msg_result = await test_db_session.execute(msg_stmt)
        messages = list(msg_result.scalars().all())

        assert len(messages) == 4
        assert messages[0].content == "Turn 1 question"
        assert messages[1].content == "Answer turn 1."
        assert messages[2].content == "Turn 2 question"
        assert messages[3].content == "Answer turn 2 building on turn 1."
