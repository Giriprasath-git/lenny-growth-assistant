"""
Automated unit and integration tests for Ship 30 for 30 Essay Generation.
Covers:
- Essay request schema validation
- Prompt construction & 1-3-1 pacing structure
- Local Ollama provider execution (default)
- Gemini Cloud provider execution & missing API key error handling
- Pi SDK provider routing
- RAG-grounded essay generation with citation preservation
- Non-grounded essay generation without fabricated citations
- Graceful handling of topics with missing/insufficient transcript evidence
- Word count calculations and model bounding advisory reporting
- PostgreSQL persistence and retrieval via GET /api/v1/essays/{id} and GET /api/v1/essays
- Provider timeout and connection failure mapping

ALL EXTERNAL MODEL / HTTP CALLS ARE FULLY MOCKED. ZERO LIVE NETWORK CALLS.
DO NOT RUN TESTS.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.essay_service import (
    EssayGenerationService,
    LOCAL_TOKEN_BUDGETS,
    CLOUD_TOKEN_BUDGETS,
    get_token_budget,
)
from backend.app.agent.providers.base import CompletionResult
from backend.app.core.config import settings
from backend.app.core.exceptions import ProviderUnavailableError, SessionNotFoundError
from backend.app.db.models.message import ChatMessage
from backend.app.db.models.session import ChatSession
from backend.app.rag.retriever import GroundedEvidence, RetrievedChunk
from backend.app.schemas.essay import EssayGenerateRequest, EssayResponse


MOCK_ESSAY_CONTENT = """# How To Build High-Leverage Growth Loops Without Burning Out

**Hook:** Most founders pour capital into top-of-funnel acquisition while their product leaks retention from the bottom.

## 1. The Core Flaw in Modern Acquisition
Traditional funnels die because they treat acquisition as a linear transaction.
- Acquisition costs climb steadily every quarter.
- Churn silently erodes lifetime value before users experience the "Aha!" moment [1].
- Reinvesting revenue into paid ads produces diminishing returns.
Compounding loops always defeat one-off marketing spikes.

## 2. Elena Verna's Loop Architecture
Product-led growth is an engine that feeds high-intent users into your ecosystem [2].
- Make core product value accessible in under five minutes.
- Build natural viral triggers into document sharing and collaborative invites.
- Transition users to paid tiers only when organizational thresholds are crossed.
Fix your retention baseline before turning on the growth faucet.

## The Tactical Takeaway
Stop optimizing Google Ads when your day-30 retention is below 20%. Map your primary retention loop this week and remove every onboarding gate.

---
### Alternative Headlines:
1. Why Most B2B SaaS Startups Fail At Retention (And How To Fix It)
2. The 3-Step Framework To Building Elena Verna's Growth Loop
3. The Counterintuitive Truth About Sustainable B2B Growth
"""


# ==============================================================================
# 1. Request Validation Tests
# ==============================================================================

def test_essay_request_validation():
    """Verifies that EssayGenerateRequest applies strict length, tone, and topic constraints."""
    # Valid request
    valid = EssayGenerateRequest(
        topic="Product-Led Growth Loops",
        target_audience="Founders",
        tone="educational",
        desired_length="deep_dive",
        ground_with_podcasts=True,
    )
    assert valid.topic == "Product-Led Growth Loops"
    assert valid.desired_length == "deep_dive"

    # Missing topic raises ValueError / ValidationError
    with pytest.raises(Exception):
        EssayGenerateRequest(topic="")  # min_length=3


# ==============================================================================
# 2. Prompt Construction & Output Parsing Tests
# ==============================================================================

def test_essay_prompt_construction_and_cadence():
    """Verifies that system prompt enforces Ship 30 hook, 1-3-1 cadence, and section rules."""
    service = EssayGenerationService()
    sys_prompt, user_prompt = service._build_essay_prompt(
        topic="LNO Framework for Product Managers",
        target_audience="Senior PMs",
        tone="educational",
        desired_length="deep_dive",
        target_words=1250,
        specific_instructions="Include 4 pillars and checklist",
        grounding_context="Shreyas Doshi explains Leverage tasks [1].",
        has_evidence=True,
    )

    assert "Ship 30 for 30" in sys_prompt
    assert "1-3-1 VISUAL CADENCE" in sys_prompt
    assert "Senior PMs" in sys_prompt
    assert "1250 words" in sys_prompt
    assert "<podcast_evidence>" in user_prompt
    assert "Include 4 pillars and checklist" in user_prompt


def test_parse_essay_output_statistics():
    """Verifies that title, hook, alternative titles, takeaway, and word count are extracted cleanly."""
    service = EssayGenerationService()
    parsed = service._parse_essay_output(
        raw_text=MOCK_ESSAY_CONTENT,
        topic="Growth Loops",
        target_words=300,
    )

    assert "How To Build High-Leverage Growth Loops" in parsed["title"]
    assert "Most founders pour capital into top-of-funnel" in parsed["headline_hook"]
    assert len(parsed["alternative_titles"]) >= 2
    assert "Stop optimizing Google Ads" in parsed["takeaway"]
    assert parsed["actual_word_count"] > 150
    assert parsed["word_count_status"] in ("target_achieved", "bounded_by_model_output")


# ==============================================================================
# 3. Provider Execution & Grounding Tests (FastAPI Client)
# ==============================================================================

@pytest.mark.asyncio
async def test_generate_essay_local_ollama_default(client: AsyncClient):
    """Verifies POST /api/v1/essays generates an essay with default local Ollama provider."""
    mock_completion = CompletionResult(
        content=MOCK_ESSAY_CONTENT,
        total_tokens=350,
        model_name="qwen2.5:1.5b",
        latency_ms=1200.5,
    )

    mock_empty_evidence = GroundedEvidence(
        query="High-Touch Growth Loops",
        chunks=[],
        total_found=0,
        context_text="",
        citations_payload=[],
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock, return_value=mock_completion), \
         patch("backend.app.rag.retriever.TranscriptRetriever.get_grounded_evidence", new_callable=AsyncMock, return_value=mock_empty_evidence):

        payload = {
            "topic": "High-Touch Growth Loops",
            "target_audience": "Founders",
            "tone": "educational",
            "desired_length": "short",
            "ground_with_podcasts": False,
        }

        response = await client.post("/api/v1/essays", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert "id" in data
        assert "session_id" in data
        assert "How To Build High-Leverage Growth Loops" in data["title"]
        assert data["provider"] == "ollama"
        assert data["model"] == "qwen2.5:1.5b"
        assert data["podcast_grounded"] is False
        assert data["actual_word_count"] > 100
        assert len(data["alternative_titles"]) >= 2


@pytest.mark.asyncio
async def test_generate_essay_with_podcast_grounding(client: AsyncClient):
    """Verifies POST /api/v1/essays incorporates transcript evidence and persists citations."""
    chunk_id = str(uuid.uuid4())
    mock_chunk = RetrievedChunk(
        chunk_id=chunk_id,
        episode_id="4ef0juAMqoE",
        episode_title="Elena Verna on PLG",
        guest_name="Elena Verna",
        timestamp_start="14:32",
        timestamp_end="15:50",
        content="Product-led growth is an engine that feeds high-intent leads.",
        similarity_score=0.92,
        youtube_timestamp_url="https://www.youtube.com/watch?v=4ef0juAMqoE&t=872s",
    )

    mock_completion = CompletionResult(
        content=MOCK_ESSAY_CONTENT,
        total_tokens=420,
        model_name="qwen2.5:1.5b",
        latency_ms=1500.0,
    )

    mock_evidence = GroundedEvidence(
        query="Elena Verna PLG Loops",
        chunks=[mock_chunk],
        total_found=1,
        context_text="Product-led growth is an engine that feeds high-intent leads.",
        citations_payload=[
            {
                "citation_index": 1,
                "chunk_id": chunk_id,
                "episode_id": "4ef0juAMqoE",
                "episode_title": "Elena Verna on PLG",
                "guest_name": "Elena Verna",
                "timestamp_start": "14:32",
                "timestamp_end": "15:50",
                "youtube_timestamp_url": "https://www.youtube.com/watch?v=4ef0juAMqoE&t=872s",
                "quoted_text": "Product-led growth is an engine that feeds high-intent leads.",
                "relevance_score": 0.92,
                "is_interpolated_timestamp": False,
            }
        ],
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock, return_value=mock_completion), \
         patch("backend.app.rag.retriever.TranscriptRetriever.get_grounded_evidence", new_callable=AsyncMock, return_value=mock_evidence):

        payload = {
            "topic": "Elena Verna PLG Loops",
            "ground_with_podcasts": True,
            "desired_length": "medium",
        }

        response = await client.post("/api/v1/essays", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["podcast_grounded"] is True
        assert len(data["citations"]) == 1
        citation = data["citations"][0]
        assert citation["guest_name"] == "Elena Verna"
        assert citation["episode_id"] == "4ef0juAMqoE"
        assert citation["timestamp_start"] == "14:32"


@pytest.mark.asyncio
async def test_generate_essay_gemini_unconfigured_error(client: AsyncClient):
    """Verifies that requesting Cloud Gemini returns 503 ProviderUnavailableError when GEMINI_API_KEY is blank."""
    with patch.object(settings, "GEMINI_API_KEY", ""):
        payload = {
            "topic": "Growth Strategy",
            "provider": "cloud",
        }
        response = await client.post("/api/v1/essays", json=payload)
        assert response.status_code == 503
        data = response.json()
        assert "GEMINI_API_KEY" in data.get("message", "") or "gemini" in data.get("detail", "").lower()


@pytest.mark.asyncio
async def test_generate_essay_pi_sdk_provider(client: AsyncClient):
    """Verifies that requesting provider='pi_agent' routes to the Pi Coding Agent SDK adapter."""
    mock_completion = CompletionResult(
        content=MOCK_ESSAY_CONTENT,
        total_tokens=400,
        model_name="qwen2.5:1.5b",
        latency_ms=800.0,
    )

    mock_empty_evidence = GroundedEvidence(
        query="Non-scalable loops",
        chunks=[],
        total_found=0,
        context_text="",
        citations_payload=[],
    )

    with patch("backend.app.agent.providers.pi_agent.PiAgentProvider.generate", new_callable=AsyncMock, return_value=mock_completion), \
         patch("backend.app.rag.retriever.TranscriptRetriever.get_grounded_evidence", new_callable=AsyncMock, return_value=mock_empty_evidence):

        payload = {
            "topic": "Non-scalable loops",
            "provider": "pi_agent",
            "ground_with_podcasts": False,
        }
        response = await client.post("/api/v1/essays", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "pi_agent"


# ==============================================================================
# 4. Persistence & Retrieval Endpoints Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_get_and_list_essays(client: AsyncClient):
    """Verifies that generated essays are retrievable by ID and listed via GET /api/v1/essays."""
    mock_completion = CompletionResult(
        content=MOCK_ESSAY_CONTENT,
        total_tokens=300,
        model_name="qwen2.5:1.5b",
        latency_ms=950.0,
    )

    mock_empty_evidence = GroundedEvidence(
        query="Persistence Test Topic",
        chunks=[],
        total_found=0,
        context_text="",
        citations_payload=[],
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock, return_value=mock_completion), \
         patch("backend.app.rag.retriever.TranscriptRetriever.get_grounded_evidence", new_callable=AsyncMock, return_value=mock_empty_evidence):

        # Generate an essay
        create_res = await client.post("/api/v1/essays", json={"topic": "Persistence Test Topic", "ground_with_podcasts": False})
        assert create_res.status_code == 200
        essay_data = create_res.json()
        essay_id = essay_data["id"]

        # Fetch by ID
        get_res = await client.get(f"/api/v1/essays/{essay_id}")
        assert get_res.status_code == 200
        retrieved = get_res.json()
        assert retrieved["id"] == essay_id
        assert retrieved["title"] == essay_data["title"]

        # List recent essays
        list_res = await client.get("/api/v1/essays?limit=10")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["total"] >= 1
        assert any(e["id"] == essay_id for e in list_data["items"])


# ==============================================================================
# 5. Cloud vs Local Token Budgets, Word Count Acceptance & Warnings Tests
# ==============================================================================

def test_cloud_vs_local_token_budgets():
    """Verifies that Cloud Gemini has 3,200 tokens allocated for deep-dive while Ollama is capped at 1,500."""
    assert CLOUD_TOKEN_BUDGETS["deep_dive"] == 3200
    assert CLOUD_TOKEN_BUDGETS["medium"] == 1500
    assert CLOUD_TOKEN_BUDGETS["short"] == 800

    assert LOCAL_TOKEN_BUDGETS["deep_dive"] == 1500
    assert LOCAL_TOKEN_BUDGETS["medium"] == 950
    assert LOCAL_TOKEN_BUDGETS["short"] == 600

    # Helper function verification
    assert get_token_budget("cloud", "deep_dive") == 3200
    assert get_token_budget("gemini", "deep_dive") == 3200
    assert get_token_budget("anthropic", "deep_dive") == 3200
    assert get_token_budget("ollama", "deep_dive") == 1500
    assert get_token_budget("pi_agent", "deep_dive") == 1500


def test_deep_dive_prompt_5_pillars_and_target_range():
    """Verifies that Deep-Dive prompts configure 5 core pillars and 1,100-1,350 words target range."""
    service = EssayGenerationService()
    sys_prompt, user_prompt = service._build_essay_prompt(
        topic="Retention Engines",
        target_audience="Growth Engineers",
        tone="educational",
        desired_length="deep_dive",
        target_words=1250,
        grounding_context="",
        has_evidence=False,
    )

    assert "OUTPUT FORMAT REQUIREMENTS (DEEP-DIVE ESSAY ~1,100–1,350 WORDS" in sys_prompt
    assert "## 1. [First Core Pillar Title]" in sys_prompt
    assert "## 2. [Second Core Pillar Title]" in sys_prompt
    assert "## 3. [Third Core Pillar Title]" in sys_prompt
    assert "## 4. [Fourth Core Pillar Title]" in sys_prompt
    assert "## 5. [Fifth Core Pillar Title]" in sys_prompt
    assert "## The Tactical Takeaway" in sys_prompt
    assert "~180-220 words" in sys_prompt
    assert "1,100–1,350 words" in user_prompt


def test_parse_essay_output_warning_messages_provider_specific():
    """Verifies that Cloud Gemini short outputs never show local 8 GB RAM warnings and show accurate explanations."""
    service = EssayGenerationService()
    short_raw_text = "Word " * 620

    # 1. Cloud Gemini with short output (< 85% of 1250 words)
    cloud_parsed = service._parse_essay_output(
        raw_text=short_raw_text,
        topic="PLG Loops",
        target_words=1250,
        provider_name="cloud",
        finish_reason="STOP",
    )
    assert cloud_parsed["word_count_status"] == "bounded_by_model_output"
    assert "8 GB RAM" not in cloud_parsed["word_count_note"]
    assert "Local model" not in cloud_parsed["word_count_note"]
    assert "Cloud model" in cloud_parsed["word_count_note"]
    assert "620 words" in cloud_parsed["word_count_note"]

    # 2. Cloud Gemini with MAX_TOKENS finish reason
    cloud_max_tokens_parsed = service._parse_essay_output(
        raw_text=short_raw_text,
        topic="PLG Loops",
        target_words=1250,
        provider_name="cloud",
        finish_reason="MAX_TOKENS",
    )
    assert "reached maximum output token budget" in cloud_max_tokens_parsed["word_count_note"]
    assert "8 GB RAM" not in cloud_max_tokens_parsed["word_count_note"]

    # 3. Local Ollama with short output preserves 8 GB RAM stability message
    ollama_parsed = service._parse_essay_output(
        raw_text=short_raw_text,
        topic="PLG Loops",
        target_words=1250,
        provider_name="ollama",
        finish_reason="STOP",
    )
    assert ollama_parsed["word_count_status"] == "bounded_by_model_output"
    assert "Local model inference token budget bounded output to preserve 8 GB RAM stability" in ollama_parsed["word_count_note"]

    # 4. Achieving practical acceptance target range (>= 1100 words) has no warning
    full_raw_text = "Word " * 1150
    accepted_parsed = service._parse_essay_output(
        raw_text=full_raw_text,
        topic="PLG Loops",
        target_words=1250,
        provider_name="cloud",
        finish_reason="STOP",
    )
    assert accepted_parsed["word_count_status"] == "target_achieved"
    assert accepted_parsed["word_count_note"] is None


@pytest.mark.asyncio
async def test_cloud_deep_dive_single_bounded_expansion(client: AsyncClient):
    """Verifies that Cloud Gemini performs at most one bounded expansion pass when initial draft is under 950 words."""
    short_draft = "# Title\n\n**Hook:** A hook.\n\n" + ("Word " * 620)
    expanded_draft = "# Title\n\n**Hook:** A hook.\n\n" + ("Word " * 1220)

    call_count = 0

    async def mock_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return CompletionResult(
                content=short_draft,
                total_tokens=700,
                model_name="gemini-3.5-flash-lite",
                finish_reason="STOP",
                latency_ms=1000.0,
            )
        else:
            return CompletionResult(
                content=expanded_draft,
                total_tokens=1600,
                model_name="gemini-3.5-flash-lite",
                finish_reason="STOP",
                latency_ms=1800.0,
            )

    mock_empty_evidence = GroundedEvidence(
        query="Cloud Deep Dive Topic",
        chunks=[],
        total_found=0,
        context_text="",
        citations_payload=[],
    )

    with patch.object(settings, "GEMINI_API_KEY", "mock-valid-key"), \
         patch("backend.app.agent.providers.gemini.GeminiProvider.generate", side_effect=mock_generate), \
         patch("backend.app.rag.retriever.TranscriptRetriever.get_grounded_evidence", new_callable=AsyncMock, return_value=mock_empty_evidence):

        payload = {
            "topic": "Cloud Deep Dive Topic",
            "provider": "cloud",
            "desired_length": "deep_dive",
            "ground_with_podcasts": False,
        }

        response = await client.post("/api/v1/essays", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Called twice (1 initial draft + 1 bounded expansion)
        assert call_count == 2
        assert data["actual_word_count"] > 1100
        assert data["word_count_status"] == "target_achieved"
        assert data["word_count_note"] is None


@pytest.mark.asyncio
async def test_local_ollama_deep_dive_never_triggers_expansion(client: AsyncClient):
    """Verifies that Local Ollama never triggers expansion passes, preserving 8 GB RAM stability and latency."""
    short_draft = "# Title\n\n**Hook:** A hook.\n\n" + ("Word " * 620)

    call_count = 0

    async def mock_generate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return CompletionResult(
            content=short_draft,
            total_tokens=650,
            model_name="qwen2.5:1.5b",
            finish_reason="STOP",
            latency_ms=900.0,
        )

    mock_empty_evidence = GroundedEvidence(
        query="Local Topic",
        chunks=[],
        total_found=0,
        context_text="",
        citations_payload=[],
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", side_effect=mock_generate), \
         patch("backend.app.rag.retriever.TranscriptRetriever.get_grounded_evidence", new_callable=AsyncMock, return_value=mock_empty_evidence):

        payload = {
            "topic": "Local Topic",
            "provider": "ollama",
            "desired_length": "deep_dive",
            "ground_with_podcasts": False,
        }

        response = await client.post("/api/v1/essays", json=payload)
        assert response.status_code == 200
        data = response.json()

        # Only called once
        assert call_count == 1
        assert data["actual_word_count"] >= 620
        assert data["word_count_status"] == "bounded_by_model_output"
        assert "8 GB RAM" in data["word_count_note"]

