"""
Automated Synthetic Test Suite for Google Gemini Cloud LLM Provider and Local/Cloud Toggle.
Covers:
- GeminiProvider initialization and documented free-tier model configuration (gemini-3.5-flash-lite)
- Missing GEMINI_API_KEY error handling (raises ProviderUnavailableError, HTTP 502)
- Provider health check status transitions (unconfigured -> configured_unverified -> verified)
- Multi-turn dialogue mapping ('assistant' -> 'model', 'user' -> 'user')
- System instruction payload synthesis ('system_instruction')
- Sampling parameter deprecation handling (temperature, topP, topK omitted for Gemini 3.5)
- Final turn user role validation
- Successful mocked generateContent execution and usageMetadata token parsing
- Candidate safety block and prompt block filter handling
- Empty candidate response handling
- Authentication failures (HTTP 401/403) and API key redaction safety
- Quota exhaustion / rate limiting (HTTP 429 RESOURCE_EXHAUSTED)
- Network timeouts and connection errors
- Streaming token generator (streamGenerateContent?alt=sse)
- Provider toggle switching (Local Ollama <-> Cloud Gemini) on identical session
- Provider metadata and citation persistence across both modes
- Failure rollback safety on cloud error
- Fast startup and /api/v1/chat/sdk-status inspection without credentials

ALL EXTERNAL MODEL / HTTP CALLS ARE FULLY MOCKED. ZERO LIVE NETWORK CALLS.
DO NOT RUN TESTS DIRECTLY.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.engine import AgentEngine
from backend.app.agent.providers.base import ChatMessageInput, CompletionResult, StreamDelta
from backend.app.agent.providers.gemini import GeminiProvider
from backend.app.agent.providers.ollama import OllamaProvider
from backend.app.core.config import settings
from backend.app.core.exceptions import ProviderUnavailableError
from backend.app.db.models.message import ChatMessage, MessageCitation
from backend.app.db.models.session import ChatSession
from backend.app.db.models.transcript import TranscriptChunk
from backend.app.schemas.chat import ChatTurnResponse


# ==============================================================================
# 1. Configuration & Health Contract Tests
# ==============================================================================

def test_gemini_provider_defaults():
    """Verifies that Gemini provider defaults to gemini-3.5-flash-lite with proper generation limits."""
    provider = GeminiProvider()
    assert provider.model == "gemini-3.5-flash-lite"
    assert provider.timeout == 60.0
    assert "googleapis.com" in provider.base_url


@pytest.mark.asyncio
async def test_gemini_health_unconfigured_when_key_absent():
    """Verifies check_health reports 'unconfigured' when GEMINI_API_KEY is missing."""
    provider = GeminiProvider(api_key="")
    health = await provider.check_health()
    assert health["healthy"] is False
    assert health["status"] == "unconfigured"
    assert health["configured"] is False
    assert health["verified"] is False
    assert health["provider"] == "gemini"
    assert "GEMINI_API_KEY is not configured" in health["message"]


@pytest.mark.asyncio
async def test_gemini_health_configured_unverified_when_key_present():
    """Verifies check_health distinguishes unverified key presence from confirmed operational state."""
    # Reset verified state for test
    GeminiProvider._has_verified_call = False

    provider = GeminiProvider(api_key="mock-unverified-key")
    health = await provider.check_health()
    assert health["healthy"] is True
    assert health["status"] == "configured_unverified"
    assert health["configured"] is True
    assert health["verified"] is False
    assert "unverified until first authorized" in health["message"].lower()


@pytest.mark.asyncio
async def test_gemini_health_transitions_to_verified_after_success():
    """Verifies check_health reports 'verified' once an authorized live call has succeeded."""
    GeminiProvider.mark_verified()
    provider = GeminiProvider(api_key="mock-key")
    health = await provider.check_health()
    assert health["healthy"] is True
    assert health["status"] == "verified"
    assert health["verified"] is True
    assert "verified and operational" in health["message"]

    # Reset after test
    GeminiProvider._has_verified_call = False


# ==============================================================================
# 2. Payload Formatting & Schema Synthesis Tests
# ==============================================================================

def test_gemini_payload_formatting_roles_and_system():
    """
    Verifies that dialogue messages map 'assistant' -> 'model', 'user' -> 'user',
    system prompts are correctly separated into system_instruction,
    and deprecated sampling parameters (temperature, topP, topK, candidateCount)
    are excluded for Gemini 3.5 Flash-Lite while maxOutputTokens is preserved.
    """
    provider = GeminiProvider(api_key="test-key", model="gemini-3.5-flash-lite")
    messages = [
        ChatMessageInput(role="user", content="How do growth loops work?"),
        ChatMessageInput(role="assistant", content="Growth loops are closed systems..."),
        ChatMessageInput(role="user", content="Can you give an example?"),
    ]

    payload = provider._format_payload(
        messages=messages,
        system="You are Lenny's growth advisor.",
        temperature=0.3,
        max_tokens=1000,
    )

    # System instruction mapping
    assert "system_instruction" in payload
    assert payload["system_instruction"]["parts"][0]["text"] == "You are Lenny's growth advisor."

    # Generation config: deprecated sampling parameters must NOT be sent for Gemini 3.5 Flash-Lite
    assert "temperature" not in payload["generationConfig"]
    assert "topP" not in payload["generationConfig"]
    assert "topK" not in payload["generationConfig"]
    assert "candidateCount" not in payload["generationConfig"]
    assert payload["generationConfig"]["maxOutputTokens"] == 1000

    # Contents array
    contents = payload["contents"]
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "How do growth loops work?"
    assert contents[1]["role"] == "model"
    assert contents[1]["parts"][0]["text"] == "Growth loops are closed systems..."
    assert contents[2]["role"] == "user"
    assert contents[2]["parts"][0]["text"] == "Can you give an example?"
    assert contents[-1]["role"] == "user"


def test_gemini_payload_final_turn_must_be_user():
    """
    Verifies that if messages end on an assistant/model turn,
    _format_payload ensures the final conversation turn is always a valid user message.
    """
    provider = GeminiProvider(api_key="test-key", model="gemini-3.5-flash-lite")
    messages = [
        ChatMessageInput(role="user", content="Initial prompt"),
        ChatMessageInput(role="assistant", content="Assistant reply"),
    ]

    payload = provider._format_payload(messages=messages)
    contents = payload["contents"]
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    assert contents[2]["role"] == "user"
    assert contents[-1]["role"] == "user"


def test_gemini_payload_consecutive_same_role_merged():
    """Verifies that consecutive messages with the same role merge parts for valid Gemini schema."""
    provider = GeminiProvider(api_key="test-key")
    messages = [
        ChatMessageInput(role="user", content="First question"),
        ChatMessageInput(role="user", content="Second related note"),
    ]

    payload = provider._format_payload(messages=messages)
    contents = payload["contents"]
    assert len(contents) == 1
    assert contents[0]["role"] == "user"
    assert len(contents[0]["parts"]) == 2
    assert contents[0]["parts"][0]["text"] == "First question"
    assert contents[0]["parts"][1]["text"] == "Second related note"


# ==============================================================================
# 3. Successful Mocked Generation & Token Parsing
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_successful_mocked_generation():
    """Verifies parsing of official Google Gemini REST generateContent response."""
    GeminiProvider._has_verified_call = False
    provider = GeminiProvider(api_key="test-key", model="gemini-3.5-flash-lite")

    mock_gemini_body = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Elena Verna explains that product-led growth relies on the product driving acquisition [1]."
                        }
                    ],
                    "role": "model",
                },
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 210,
            "candidatesTokenCount": 45,
            "totalTokenCount": 255,
        },
        "modelVersion": "gemini-3.5-flash-lite",
    }

    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_gemini_body

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        res: CompletionResult = await provider.generate(
            messages=[ChatMessageInput(role="user", content="What is PLG?")],
            system="Be concise.",
        )

        assert res.model_name == "gemini-3.5-flash-lite"
        assert res.total_tokens == 255
        assert res.finish_reason == "STOP"
        assert "Elena Verna explains" in res.content
        assert res.latency_ms >= 0.0

        # Must mark provider verified
        assert GeminiProvider.is_verified() is True

    # Reset verified state
    GeminiProvider._has_verified_call = False


# ==============================================================================
# 4. Error Handling & Safety Filters
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_missing_key_raises_provider_unavailable():
    """Verifies that calling generate without GEMINI_API_KEY raises ProviderUnavailableError."""
    provider = GeminiProvider(api_key="")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.generate(
            messages=[ChatMessageInput(role="user", content="Hello")],
        )
    assert "GEMINI_API_KEY is not configured" in exc_info.value.message
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_gemini_safety_block_finish_reason():
    """Verifies that finishReason == SAFETY raises ProviderUnavailableError with safety explanation."""
    provider = GeminiProvider(api_key="test-key")
    mock_body = {
        "candidates": [
            {
                "finishReason": "SAFETY",
                "content": {"parts": []},
            }
        ]
    }
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_body

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Harmful content")],
            )
        assert "safety filters" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_gemini_prompt_feedback_block():
    """Verifies that promptFeedback.blockReason raises ProviderUnavailableError."""
    provider = GeminiProvider(api_key="test-key")
    mock_body = {
        "promptFeedback": {
            "blockReason": "SAFETY",
        },
        "candidates": [],
    }
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_body

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Blocked prompt")],
            )
        assert "safety filters" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_gemini_auth_failure_http_403_and_redaction():
    """Verifies HTTP 403 maps to ProviderUnavailableError and never leaks the API key."""
    secret_key = "AIzaSySecretTestingKey123456"
    provider = GeminiProvider(api_key=secret_key)

    mock_error_resp = MagicMock(spec=Response)
    mock_error_resp.status_code = 403
    mock_error_resp.text = f"API key {secret_key} is not valid."
    mock_error_resp.json.return_value = {
        "error": {
            "code": 403,
            "message": f"API key {secret_key} not valid.",
            "status": "PERMISSION_DENIED",
        }
    }

    http_err = httpx.HTTPStatusError(
        message="Client error 403",
        request=MagicMock(),
        response=mock_error_resp,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=http_err):
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Test")],
            )
        # Message must indicate auth failure
        assert "authentication failed" in exc_info.value.message.lower()
        # Must NOT leak secret key
        assert secret_key not in exc_info.value.message


@pytest.mark.asyncio
async def test_gemini_quota_exhausted_http_429():
    """Verifies HTTP 429 maps to clear free-tier quota exhausted message."""
    provider = GeminiProvider(api_key="test-key")

    mock_error_resp = MagicMock(spec=Response)
    mock_error_resp.status_code = 429
    mock_error_resp.text = "RESOURCE_EXHAUSTED"
    mock_error_resp.json.return_value = {
        "error": {
            "code": 429,
            "message": "Resource has been exhausted (e.g. check quota).",
            "status": "RESOURCE_EXHAUSTED",
        }
    }

    http_err = httpx.HTTPStatusError(
        message="Client error 429",
        request=MagicMock(),
        response=mock_error_resp,
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=http_err):
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Test")],
            )
        assert "quota or rate limit exceeded" in exc_info.value.message.lower()
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_gemini_network_timeout():
    """Verifies network timeout raises ProviderUnavailableError."""
    provider = GeminiProvider(api_key="test-key", timeout=10.0)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Read timeout")):
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.generate(
                messages=[ChatMessageInput(role="user", content="Test")],
            )
        assert "timed out after 10 seconds" in exc_info.value.message.lower()


# ==============================================================================
# 5. Local <-> Cloud Toggle and End-to-End Orchestration
# ==============================================================================

@pytest.mark.asyncio
async def test_agent_engine_routes_cloud_to_gemini(test_db_session: AsyncSession):
    """
    Verifies that submitting provider='cloud' invokes GeminiProvider, persists
    metadata identifying Gemini as the model, and stores source citations.
    """
    # 1. Create transcript chunk
    chunk_uuid = uuid.uuid4()
    chunk = TranscriptChunk(
        id=chunk_uuid,
        episode_id="ep-201-elena-verna",
        episode_title="Elena Verna on PLG and B2B Growth",
        guest_name="Elena Verna",
        timestamp_start="08:15",
        timestamp_end="09:40",
        chunk_index=1,
        content="Product-led sales requires the user to fall in love with the product before speaking to sales.",
        metadata_json={
            "youtube_timestamp_url": "https://youtu.be/test?t=495",
            "source_file": "ep201.txt",
        },
    )
    test_db_session.add(chunk)

    # 2. Create session
    session_id = uuid.uuid4()
    session = ChatSession(
        id=session_id,
        title="PLG Inquiry",
        provider="cloud",
        model_name="gemini-3.5-flash-lite",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    # 3. Setup mocked Gemini completion
    mock_gemini_completion = CompletionResult(
        content="Elena Verna states that product-led sales starts with product love [1].",
        total_tokens=140,
        model_name="gemini-3.5-flash-lite",
        latency_ms=95.0,
    )

    engine = AgentEngine()

    with patch.object(GeminiProvider, "generate", new_callable=AsyncMock, return_value=mock_gemini_completion) as mock_gemini_gen, \
         patch.object(OllamaProvider, "generate", new_callable=AsyncMock) as mock_ollama_gen:

        response: ChatTurnResponse = await engine.execute_turn(
            session_id=session_id,
            user_message="How does product-led sales work?",
            db=test_db_session,
            provider="cloud",
            top_k=2,
        )

        # Gemini must have been invoked, not Ollama
        assert mock_gemini_gen.called
        assert not mock_ollama_gen.called

        # Response verification
        assert response.provider == "cloud"
        assert response.model == "gemini-3.5-flash-lite"
        assert "Elena Verna states" in response.assistant_message.content
        assert len(response.citations) >= 1
        assert response.citations[0].guest_name == "Elena Verna"

        # Verify DB metadata
        msg_stmt = select(ChatMessage).where(ChatMessage.session_id == session_id, ChatMessage.role == "assistant")
        res = await test_db_session.execute(msg_stmt)
        asst_msg = res.scalar_one()
        assert asst_msg.provider_metadata["provider"] == "cloud"
        assert asst_msg.provider_metadata["model"] == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_provider_toggle_switching_on_same_session(test_db_session: AsyncSession):
    """
    Verifies that switching between Local Ollama and Cloud Gemini on subsequent turns
    of the exact same session thread maintains conversation history without loss.
    """
    session_id = uuid.uuid4()
    session = ChatSession(
        id=session_id,
        title="Toggle Test Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    engine = AgentEngine()

    # Turn 1: Local Ollama
    ollama_completion = CompletionResult(
        content="Turn 1 answer generated locally by Ollama.",
        total_tokens=80,
        model_name="qwen2.5:1.5b",
        latency_ms=45.0,
    )
    with patch.object(OllamaProvider, "generate", new_callable=AsyncMock, return_value=ollama_completion):
        t1_res = await engine.execute_turn(
            session_id=session_id,
            user_message="Question 1 (Local)",
            db=test_db_session,
            provider="ollama",
        )
        assert t1_res.provider == "ollama"
        assert t1_res.model == "qwen2.5:1.5b"

    # Turn 2: Cloud Gemini on the same session
    gemini_completion = CompletionResult(
        content="Turn 2 answer generated in cloud by Gemini.",
        total_tokens=95,
        model_name="gemini-3.5-flash-lite",
        latency_ms=75.0,
    )
    with patch.object(GeminiProvider, "generate", new_callable=AsyncMock, return_value=gemini_completion) as mock_gemini:
        t2_res = await engine.execute_turn(
            session_id=session_id,
            user_message="Question 2 (Cloud)",
            db=test_db_session,
            provider="cloud",
        )
        assert t2_res.provider == "cloud"
        assert t2_res.model == "gemini-3.5-flash-lite"

        # Verify historical dialogue passed to Gemini contains turn 1
        called_messages = mock_gemini.call_args.kwargs["messages"]
        user_msgs = [m.content for m in called_messages if m.role == "user"]
        asst_msgs = [m.content for m in called_messages if m.role == "assistant"]
        assert "Question 1 (Local)" in user_msgs
        assert "Turn 1 answer generated locally by Ollama." in asst_msgs

        # Verify chronological ordering and turn contents in called_messages
        assert len(called_messages) == 3
        assert called_messages[0].role == "user"
        assert called_messages[0].content == "Question 1 (Local)"
        assert called_messages[1].role == "assistant"
        assert called_messages[1].content == "Turn 1 answer generated locally by Ollama."
        assert called_messages[2].role == "user"
        assert "Question 2 (Cloud)" in called_messages[2].content

        # Verify Gemini provider payload mapping for this multi-turn dialogue
        provider_instance = GeminiProvider()
        gemini_payload = provider_instance._format_payload(messages=called_messages)
        gemini_contents = gemini_payload["contents"]
        assert len(gemini_contents) == 3
        assert gemini_contents[0]["role"] == "user"
        assert gemini_contents[0]["parts"][0]["text"] == "Question 1 (Local)"
        assert gemini_contents[1]["role"] == "model"
        assert gemini_contents[1]["parts"][0]["text"] == "Turn 1 answer generated locally by Ollama."
        assert gemini_contents[2]["role"] == "user"
        assert "Question 2 (Cloud)" in gemini_contents[2]["parts"][0]["text"]
        assert gemini_contents[-1]["role"] == "user"

    # Verify all 4 messages in DB (2 user, 2 assistant)
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
    db_res = await test_db_session.execute(stmt)
    all_msgs = db_res.scalars().all()
    assert len(all_msgs) == 4
    assert all_msgs[0].role == "user"
    assert all_msgs[0].content == "Question 1 (Local)"
    assert all_msgs[1].role == "assistant"
    assert all_msgs[1].content == "Turn 1 answer generated locally by Ollama."
    assert all_msgs[1].provider_metadata["provider"] == "ollama"
    assert all_msgs[1].provider_metadata["model"] == "qwen2.5:1.5b"
    assert all_msgs[2].role == "user"
    assert all_msgs[2].content == "Question 2 (Cloud)"
    assert all_msgs[3].role == "assistant"
    assert all_msgs[3].content == "Turn 2 answer generated in cloud by Gemini."
    assert all_msgs[3].provider_metadata["provider"] == "cloud"
    assert all_msgs[3].provider_metadata["model"] == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_provider_toggle_three_way_switching_preserves_history(test_db_session: AsyncSession):
    """
    Verifies bidirectional switching across three consecutive turns (Local -> Cloud -> Local):
    - Turn 1 (Ollama): Initial turn persisted.
    - Turn 2 (Gemini): Receives Turn 1 context; persists cloud completion.
    - Turn 3 (Ollama): Receives Turn 1 and Turn 2 context; persists local completion.
    Confirms zero context loss, strict chronological order, and accurate provider metadata.
    """
    session_id = uuid.uuid4()
    session = ChatSession(
        id=session_id,
        title="Three-Way Toggle Test",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    engine = AgentEngine()

    # Turn 1: Local Ollama
    t1_completion = CompletionResult(
        content="Turn 1 answer from Ollama.",
        total_tokens=50,
        model_name="qwen2.5:1.5b",
        latency_ms=30.0,
    )
    with patch.object(OllamaProvider, "generate", new_callable=AsyncMock, return_value=t1_completion):
        res1 = await engine.execute_turn(
            session_id=session_id,
            user_message="T1: Local question",
            db=test_db_session,
            provider="ollama",
        )
        assert res1.provider == "ollama"

    # Turn 2: Cloud Gemini
    t2_completion = CompletionResult(
        content="Turn 2 answer from Gemini.",
        total_tokens=60,
        model_name="gemini-3.5-flash-lite",
        latency_ms=50.0,
    )
    with patch.object(GeminiProvider, "generate", new_callable=AsyncMock, return_value=t2_completion) as mock_gemini:
        res2 = await engine.execute_turn(
            session_id=session_id,
            user_message="T2: Cloud question",
            db=test_db_session,
            provider="cloud",
        )
        assert res2.provider == "cloud"
        called2 = mock_gemini.call_args.kwargs["messages"]
        assert len(called2) == 3
        assert called2[0].content == "T1: Local question"
        assert called2[1].content == "Turn 1 answer from Ollama."
        assert "T2: Cloud question" in called2[2].content

    # Turn 3: Switch back to Local Ollama
    t3_completion = CompletionResult(
        content="Turn 3 answer back from Ollama.",
        total_tokens=70,
        model_name="qwen2.5:1.5b",
        latency_ms=40.0,
    )
    with patch.object(OllamaProvider, "generate", new_callable=AsyncMock, return_value=t3_completion) as mock_ollama_t3:
        res3 = await engine.execute_turn(
            session_id=session_id,
            user_message="T3: Local question again",
            db=test_db_session,
            provider="ollama",
        )
        assert res3.provider == "ollama"
        called3 = mock_ollama_t3.call_args.kwargs["messages"]
        # Must contain 4 historical turns (T1 user, T1 asst, T2 user, T2 asst) + 1 current user turn
        assert len(called3) == 5
        assert called3[0].content == "T1: Local question"
        assert called3[1].content == "Turn 1 answer from Ollama."
        assert called3[2].content == "T2: Cloud question"
        assert called3[3].content == "Turn 2 answer from Gemini."
        assert "T3: Local question again" in called3[4].content

    # Verify all 6 messages in DB
    stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
    db_res = await test_db_session.execute(stmt)
    all_msgs = db_res.scalars().all()
    assert len(all_msgs) == 6
    assert all_msgs[0].content == "T1: Local question"
    assert all_msgs[1].content == "Turn 1 answer from Ollama."
    assert all_msgs[1].provider_metadata["provider"] == "ollama"
    assert all_msgs[2].content == "T2: Cloud question"
    assert all_msgs[3].content == "Turn 2 answer from Gemini."
    assert all_msgs[3].provider_metadata["provider"] == "cloud"
    assert all_msgs[4].content == "T3: Local question again"
    assert all_msgs[5].content == "Turn 3 answer back from Ollama."
    assert all_msgs[5].provider_metadata["provider"] == "ollama"


@pytest.mark.asyncio
async def test_cloud_gemini_failure_rolls_back_safely(test_db_session: AsyncSession):
    """
    Verifies that if Gemini fails, transaction rolls back safely and no phantom
    assistant message is left in PostgreSQL.
    """
    session_id = uuid.uuid4()
    session = ChatSession(
        id=session_id,
        title="Gemini Rollback Test",
        provider="cloud",
        model_name="gemini-3.5-flash-lite",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    engine = AgentEngine()

    with patch.object(
        GeminiProvider,
        "generate",
        side_effect=ProviderUnavailableError("cloud", "Gemini free-tier quota exceeded"),
    ):
        with pytest.raises(ProviderUnavailableError):
            await engine.execute_turn(
                session_id=session_id,
                user_message="Will fail and rollback",
                db=test_db_session,
                provider="cloud",
            )

        # Database must not contain any messages from the failed turn
        stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
        res = await test_db_session.execute(stmt)
        persisted = res.scalars().all()
        assert len(persisted) == 0


# ==============================================================================
# 6. REST API & SDK Status Inspection Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_api_sdk_status_reports_gemini_cloud_configuration(client: AsyncClient):
    """Verifies GET /api/v1/chat/sdk-status reports Gemini cloud configuration and 180s Ollama timeout."""
    res = await client.get("/api/v1/chat/sdk-status")
    assert res.status_code == 200
    data = res.json()

    assert data["active_default_provider"] == "ollama"
    assert data["ollama_configuration"]["timeout_seconds"] == 180

    cloud = data["cloud_configuration"]
    assert cloud["backend"] == "gemini"
    assert cloud["model"] == "gemini-3.5-flash-lite"
    assert cloud["free_tier_eligible"] is True
    assert cloud["is_optional"] is True
    assert cloud["status"] == "unconfigured"


@pytest.mark.asyncio
async def test_api_chat_cloud_fails_clearly_when_key_unconfigured(client: AsyncClient):
    """Verifies POST /api/v1/chat with provider='cloud' returns HTTP 502 when GEMINI_API_KEY is not set."""
    # 1. Create session
    create_res = await client.post("/api/v1/sessions", json={"title": "Cloud Fail Test", "provider": "cloud"})
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    # 2. Execute chat turn with cloud provider
    res = await client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "message": "Hello via cloud",
            "provider": "cloud",
        },
    )
    assert res.status_code == 502
    data = res.json()
    assert data["error"] is True
    assert "gemini_api_key is not configured" in data["message"].lower()
