"""
Comprehensive unit and integration tests for Phase 7 Artifact Generation and Secure Downloads.
Uses isolated in-memory SQLite fixtures and mocked LLM providers (zero external API calls).
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.artifact_service import ArtifactGenerationService
from backend.app.agent.providers.base import CompletionResult
from backend.app.db.models.artifact import Artifact
from backend.app.db.models.message import ChatMessage
from backend.app.db.models.session import ChatSession


@pytest.mark.asyncio
async def test_markdown_artifact_generation(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies end-to-end Markdown strategy artifact generation and persistence."""
    # 1. Create chat session
    session = ChatSession(
        id=uuid.uuid4(),
        title="Strategy Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.flush()

    # 2. Add sample prior message
    msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="assistant",
        content="Elena Verna emphasizes that B2B product-led growth requires fixing churn before scaling top of funnel.",
    )
    test_db_session.add(msg)
    await test_db_session.commit()

    # 3. Mock Ollama generation
    mock_md = (
        "# B2B PLG Retention Strategy Playbook\n\n"
        "Executive Summary: Retention is the fundamental engine of growth.\n\n"
        "## Core Pillars\n"
        "- Pillar 1: Activation milestones\n"
        "- Pillar 2: Feature adoption loops\n\n"
        "| Metric | Target | Owner |\n"
        "| Day 7 Retention | >40% | Growth Team |\n"
        "| Day 30 Retention | >25% | Product Team |\n"
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = CompletionResult(
            content=mock_md,
            model_name="qwen2.5:1.5b",
            total_tokens=240,
        )

        res = await client.post(
            "/api/v1/artifacts",
            json={
                "session_id": str(session.id),
                "message_id": str(msg.id),
                "artifact_type": "markdown",
                "instructions": "Create an executive strategy document",
            },
        )

        assert res.status_code == 201
        data = res.json()
        assert data["artifact_type"] == "markdown"
        assert "B2B PLG Retention Strategy Playbook" in data["title"]
        assert "Day 7 Retention" in data["content"]
        assert data["provider"] == "ollama"

        # Verify persisted in artifacts table
        art_stmt = select(Artifact).where(Artifact.id == uuid.UUID(data["id"]))
        art_res = await test_db_session.execute(art_stmt)
        persisted = art_res.scalar_one_or_none()
        assert persisted is not None
        assert persisted.session_id == session.id
        assert persisted.title == data["title"]


@pytest.mark.asyncio
async def test_html_artifact_generation_and_sanitization(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies HTML artifact generation, CSS theme injection, and CSP meta insertion."""
    session = ChatSession(
        id=uuid.uuid4(),
        title="Visual Framework Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    mock_html = (
        "<!DOCTYPE html><html><head><title>Growth Scorecard</title><style>.card { background: #1e293b; }</style></head>"
        "<body><h1>Growth Scorecard</h1><div class='card'>Metric: 10x</div></body></html>"
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = CompletionResult(
            content=mock_html,
            model_name="qwen2.5:1.5b",
            total_tokens=180,
        )

        res = await client.post(
            "/api/v1/artifacts",
            json={
                "session_id": str(session.id),
                "artifact_type": "html",
                "title": "PLG Growth Scorecard",
            },
        )

        assert res.status_code == 201
        data = res.json()
        assert data["artifact_type"] == "html"
        assert data["title"] == "PLG Growth Scorecard"
        assert "Content-Security-Policy" in data["content"]
        assert "script-src 'none'" in data["content"]


def test_html_sanitization_blocks_scripts_and_handlers():
    """Directly verifies that malicious script tags, event handlers, and embeds are stripped."""
    service = ArtifactGenerationService()

    malicious_html = (
        "<!DOCTYPE html><html><head><title>Test</title></head><body>"
        "<script>alert('XSS Attack');</script>"
        "<div onclick=\"stealCookies()\" onmouseover=\"evil()\">Click Me</div>"
        "<a href=\"javascript:doHaram()\">Link</a>"
        "<iframe src=\"https://malicious.com\"></iframe>"
        "<object data=\"malicious.swf\"></object>"
        "<h1>Safe Heading</h1>"
        "</body></html>"
    )

    cleaned, was_sanitized, policy = service.sanitize_html(malicious_html)

    assert was_sanitized is True
    assert "<script>" not in cleaned
    assert "alert('XSS Attack')" not in cleaned
    assert "onclick=" not in cleaned
    assert "onmouseover=" not in cleaned
    assert "javascript:" not in cleaned
    assert "<iframe" not in cleaned
    assert "<object" not in cleaned
    assert "<h1>Safe Heading</h1>" in cleaned
    assert "Content-Security-Policy" in cleaned
    assert "script_tags" in policy["blocked_features"]
    assert "inline_event_handlers" in policy["blocked_features"]


def test_markdown_sanitization_neutralizes_raw_scripts():
    """Verifies that active script tags inside Markdown are neutralized."""
    service = ArtifactGenerationService()

    malicious_md = (
        "# Product Strategy\n\n"
        "<script>alert('hack');</script>\n\n"
        "Legitimate markdown content.\n"
        "<button onclick=\"pwn()\">Button</button>"
    )

    cleaned, was_sanitized, policy = service.sanitize_markdown(malicious_md)

    assert was_sanitized is True
    assert "<script>" not in cleaned
    assert "&lt;script" in cleaned
    assert "onclick=" not in cleaned
    assert "# Product Strategy" in cleaned


@pytest.mark.asyncio
async def test_artifact_retrieval_and_session_list(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies retrieving single artifacts and listing artifacts belonging to a session."""
    session = ChatSession(
        id=uuid.uuid4(),
        title="Multi-Artifact Session",
    )
    test_db_session.add(session)
    await test_db_session.flush()

    art1 = Artifact(
        id=uuid.uuid4(),
        session_id=session.id,
        artifact_type="markdown",
        title="Playbook 1",
        content="# Playbook 1 Content",
    )
    art2 = Artifact(
        id=uuid.uuid4(),
        session_id=session.id,
        artifact_type="html",
        title="Deliverable 2",
        content="<html><body>Deliverable 2</body></html>",
    )
    test_db_session.add_all([art1, art2])
    await test_db_session.commit()

    # 1. Fetch single artifact
    get_res = await client.get(f"/api/v1/artifacts/{art1.id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Playbook 1"

    # 2. List artifacts for session via /artifacts?session_id=...
    list_res = await client.get(f"/api/v1/artifacts?session_id={session.id}")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 2

    # 3. List via /sessions/{session_id}/artifacts
    session_art_res = await client.get(f"/api/v1/sessions/{session.id}/artifacts")
    assert session_art_res.status_code == 200
    assert len(session_art_res.json()) == 2

    # 4. Nonexistent artifact returns 404
    missing_res = await client.get(f"/api/v1/artifacts/{uuid.uuid4()}")
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_artifact_download_endpoint_headers_and_filename(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies download endpoint headers: attachment disposition, nosniff, and safe filename."""
    session = ChatSession(id=uuid.uuid4(), title="Download Test")
    test_db_session.add(session)
    await test_db_session.flush()

    # Artifact with spaces and special chars in title
    artifact = Artifact(
        id=uuid.uuid4(),
        session_id=session.id,
        artifact_type="html",
        title="Elena's B2B PLG / Retention & Growth!!",
        content="<!DOCTYPE html><html><body><h1>Self-Contained Content</h1></body></html>",
    )
    test_db_session.add(artifact)
    await test_db_session.commit()

    dl_res = await client.get(f"/api/v1/artifacts/{artifact.id}/download")
    assert dl_res.status_code == 200
    assert dl_res.headers["Content-Type"].startswith("text/html")
    assert dl_res.headers["X-Content-Type-Options"] == "nosniff"

    # Attachment disposition prevents execution under API origin
    disp = dl_res.headers["Content-Disposition"]
    assert "attachment;" in disp
    assert ".html" in disp
    # Verifies path traversal chars (/) and quotes were stripped
    assert "/" not in disp.split("filename=")[1]
    assert dl_res.text == artifact.content


@pytest.mark.asyncio
async def test_provider_routing_gemini_unconfigured_error(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies clean HTTP 503 error with actionable advice when unconfigured Cloud is requested."""
    session = ChatSession(id=uuid.uuid4(), title="Cloud Test")
    test_db_session.add(session)
    await test_db_session.commit()

    with patch("backend.app.core.config.settings.GEMINI_API_KEY", ""):
        res = await client.post(
            "/api/v1/artifacts",
            json={
                "session_id": str(session.id),
                "artifact_type": "markdown",
                "provider": "cloud",
            },
        )
        assert res.status_code == 503
        detail = res.json()["detail"].lower()
        assert "gemini" in detail
        assert "not configured" in detail


@pytest.mark.asyncio
async def test_artifact_cascade_deletion_with_session(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies that deleting a session cleanly cascades and deletes associated artifacts."""
    session = ChatSession(id=uuid.uuid4(), title="Cascade Session")
    test_db_session.add(session)
    await test_db_session.flush()

    artifact = Artifact(
        id=uuid.uuid4(),
        session_id=session.id,
        artifact_type="markdown",
        title="Cascade Playbook",
        content="Content to be deleted",
    )
    test_db_session.add(artifact)
    await test_db_session.commit()

    # Delete session
    del_res = await client.delete(f"/api/v1/sessions/{session.id}")
    assert del_res.status_code == 204

    # Query artifact directly
    art_stmt = select(Artifact).where(Artifact.id == artifact.id)
    art_res = await test_db_session.execute(art_stmt)
    assert art_res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_html_artifact_code_fence_normalization():
    """Verifies that sanitize_html correctly strips enclosing ```html, ```HTML, or ``` fences while preserving internal code blocks."""
    service = ArtifactGenerationService()

    # 1. Enclosed with ```html ... ```
    raw_fenced_1 = (
        "```html\n"
        "<!DOCTYPE html>\n"
        "<html><head><title>Dashboard</title></head><body><h1>Metrics</h1></body></html>\n"
        "```"
    )
    cleaned_1, was_san_1, policy_1 = service.sanitize_html(raw_fenced_1)
    assert not cleaned_1.startswith("```")
    assert not cleaned_1.endswith("```")
    assert "<!DOCTYPE html>" in cleaned_1
    assert "Content-Security-Policy" in cleaned_1
    assert was_san_1 is True

    # 2. Enclosed with uppercase ```HTML ... ```
    raw_fenced_2 = (
        "```HTML\n"
        "<!DOCTYPE html>\n"
        "<html><head></head><body><div>Card</div></body></html>\n"
        "```"
    )
    cleaned_2, was_san_2, policy_2 = service.sanitize_html(raw_fenced_2)
    assert not cleaned_2.startswith("```")
    assert not cleaned_2.endswith("```")
    assert "Card" in cleaned_2

    # 3. HTML containing an internal code block in <pre><code>```python print(1)```</code></pre>
    raw_with_inner = (
        "```html\n"
        "<!DOCTYPE html>\n"
        "<html><head></head><body>\n"
        "<pre><code>```python\nx = 42\n```</code></pre>\n"
        "</body></html>\n"
        "```"
    )
    cleaned_3, _, _ = service.sanitize_html(raw_with_inner)
    assert not cleaned_3.startswith("```html")
    assert "<pre><code>```python" in cleaned_3


@pytest.mark.asyncio
async def test_artifact_metadata_attribution_not_stored(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies that get_artifact and list_session_artifacts return genuine provider and model attribution from the session rather than hardcoded 'stored'."""
    session = ChatSession(
        id=uuid.uuid4(),
        title="Attribution Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.flush()

    artifact = Artifact(
        id=uuid.uuid4(),
        session_id=session.id,
        artifact_type="markdown",
        title="Verified Attribution Document",
        content="# Growth Document\n\nVerified content.",
    )
    test_db_session.add(artifact)
    await test_db_session.commit()

    # Test single get endpoint
    res = await client.get(f"/api/v1/artifacts/{artifact.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "ollama"
    assert data["model_name"] == "qwen2.5:1.5b"
    assert data["provider"] != "stored"
    assert data["model_name"] != "stored"

    # Test list endpoint
    list_res = await client.get(f"/api/v1/artifacts?session_id={session.id}")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert len(list_data["items"]) >= 1
    first_item = list_data["items"][0]
    assert first_item["provider"] == "ollama"
    assert first_item["model_name"] == "qwen2.5:1.5b"
    assert first_item["provider"] != "stored"
    assert first_item["model_name"] != "stored"


@pytest.mark.asyncio
async def test_html_artifact_rejects_truncated_css(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies that an HTML artifact with truncated CSS (ending abruptly in 'color: var') is rejected with HTTP 422."""
    session = ChatSession(
        id=uuid.uuid4(),
        title="Truncated HTML Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    # Incomplete HTML ending mid-CSS
    truncated_html = (
        "<!DOCTYPE html><html><head><title>PMF Blueprint</title><style>\n"
        ":root { --bg: #0f172a; }\n"
        "p, ul {\n"
        "    color: var"
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = CompletionResult(
            content=truncated_html,
            model_name="qwen2.5:1.5b",
            total_tokens=1200,
            finish_reason="MAX_TOKENS",
        )

        res = await client.post(
            "/api/v1/artifacts",
            json={
                "session_id": str(session.id),
                "artifact_type": "html",
                "title": "Product-Market Fit Blueprint",
            },
        )

        assert res.status_code == 422
        data = res.json()
        assert "incomplete" in data["detail"].lower()

        # Verify nothing was saved in the database
        art_stmt = select(Artifact).where(Artifact.session_id == session.id)
        art_res = await test_db_session.execute(art_stmt)
        assert art_res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_html_artifact_rejects_missing_body(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies that an HTML artifact with a head but no body section is rejected with HTTP 422."""
    session = ChatSession(
        id=uuid.uuid4(),
        title="No Body Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    no_body_html = "<!DOCTYPE html><html><head><title>Test</title><style>body{color:#fff;}</style></head></html>"

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = CompletionResult(
            content=no_body_html,
            model_name="qwen2.5:1.5b",
            total_tokens=150,
            finish_reason="STOP",
        )

        res = await client.post(
            "/api/v1/artifacts",
            json={
                "session_id": str(session.id),
                "artifact_type": "html",
                "title": "Empty Body Artifact",
            },
        )

        assert res.status_code == 422
        assert "body" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_html_artifact_normalizes_fences_and_passes(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies that complete HTML enclosed in markdown code fences is cleanly normalized, saved, and given CSP."""
    session = ChatSession(
        id=uuid.uuid4(),
        title="Fenced Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    fenced_html = (
        "```html\n"
        "<!DOCTYPE html><html><head><title>Valid Dashboard</title><style>.card{padding:10px;}</style></head>"
        "<body><h1>Valid Growth Dashboard</h1><div class='card'>Active Metric: 98%</div></body></html>\n"
        "```"
    )

    with patch("backend.app.agent.providers.ollama.OllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = CompletionResult(
            content=fenced_html,
            model_name="qwen2.5:1.5b",
            total_tokens=220,
            finish_reason="STOP",
        )

        res = await client.post(
            "/api/v1/artifacts",
            json={
                "session_id": str(session.id),
                "artifact_type": "html",
                "title": "Valid Dashboard",
            },
        )

        assert res.status_code == 201
        data = res.json()
        assert not data["content"].startswith("```")
        assert not data["content"].endswith("```")
        assert "Active Metric: 98%" in data["content"]
        assert "Content-Security-Policy" in data["content"]


@pytest.mark.asyncio
async def test_cloud_attribution_preserved_in_local_session(client: AsyncClient, test_db_session: AsyncSession):
    """Verifies that generating with Cloud Gemini inside an Ollama session preserves Cloud attribution on retrieval."""
    session = ChatSession(
        id=uuid.uuid4(),
        title="Mixed Mode Session",
        provider="ollama",
        model_name="qwen2.5:1.5b",
    )
    test_db_session.add(session)
    await test_db_session.commit()

    complete_md = "# Cloud Generated Strategy\n\nExecutive Summary: Generated using Gemini Cloud text generation."

    with patch("backend.app.agent.providers.gemini.GeminiProvider.is_configured", True):
        with patch("backend.app.agent.providers.gemini.GeminiProvider.generate", new_callable=AsyncMock) as mock_gemini:
            mock_gemini.return_value = CompletionResult(
                content=complete_md,
                model_name="gemini-3.5-flash-lite",
                total_tokens=260,
                finish_reason="STOP",
            )

            # Request generation explicitly using cloud provider
            res = await client.post(
                "/api/v1/artifacts",
                json={
                    "session_id": str(session.id),
                    "artifact_type": "markdown",
                    "title": "Cloud Deliverable",
                    "provider": "cloud",
                },
            )

            assert res.status_code == 201
            data = res.json()
            assert data["provider"] == "cloud"
            assert data["model_name"] == "gemini-3.5-flash-lite"

            # Verify retrieval reflects cloud attribution, NOT session's default ollama
            get_res = await client.get(f"/api/v1/artifacts/{data['id']}")
            assert get_res.status_code == 200
            get_data = get_res.json()
            assert get_data["provider"] == "cloud"
            assert get_data["model_name"] == "gemini-3.5-flash-lite"


