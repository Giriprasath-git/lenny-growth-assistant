"""
Automated unit and integration tests for Chat Sessions and Message Persistence.
Covers:
- Session creation
- Session retrieval
- Session independence & isolation
- Message persistence
- Missing session handling (404)
- Invalid request validation (422)
- Session deletion (204)
- Database connection failure handling (503)
"""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_session(client: AsyncClient):
    """Verifies that POST /api/v1/sessions creates a session with status 201."""
    payload = {
        "title": "Growth Retention Loop Discussion",
        "provider": "cloud",
        "model_name": "claude-3-5-sonnet-20241022",
        "user_metadata": {"cohort": "B2B SaaS", "plan": "growth"},
    }
    response = await client.post("/api/v1/sessions", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "Growth Retention Loop Discussion"
    assert data["provider"] == "cloud"
    assert data["user_metadata"] == {"cohort": "B2B SaaS", "plan": "growth"}


@pytest.mark.asyncio
async def test_list_sessions_pagination(client: AsyncClient):
    """Verifies that GET /api/v1/sessions returns a paginated list with total count."""
    # Create 3 test sessions
    for i in range(3):
        await client.post("/api/v1/sessions", json={"title": f"Session {i}"})

    response = await client.get("/api/v1/sessions?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert data["limit"] == 2
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_get_session_by_id(client: AsyncClient):
    """Verifies that GET /api/v1/sessions/{id} returns the session with empty messages initially."""
    create_res = await client.post("/api/v1/sessions", json={"title": "Roadmap Evaluation"})
    session_id = create_res.json()["id"]

    get_res = await client.get(f"/api/v1/sessions/{session_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["id"] == session_id
    assert data["title"] == "Roadmap Evaluation"
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_get_missing_session_returns_404(client: AsyncClient):
    """Verifies that querying a non-existent session UUID returns HTTP 404."""
    random_id = str(uuid.uuid4())
    response = await client.get(f"/api/v1/sessions/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] is True
    assert "not found" in data["message"].lower()


@pytest.mark.asyncio
async def test_invalid_uuid_returns_422(client: AsyncClient):
    """Verifies that passing a malformed UUID returns HTTP 422 Unprocessable Entity."""
    response = await client.get("/api/v1/sessions/not-a-valid-uuid-string")
    assert response.status_code == 422
    data = response.json()
    assert data["error"] is True
    assert "validation" in data["message"].lower()


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient):
    """Verifies that DELETE /api/v1/sessions/{id} returns 204 and removes the session."""
    create_res = await client.post("/api/v1/sessions", json={"title": "To Be Deleted"})
    session_id = create_res.json()["id"]

    # Delete session
    del_res = await client.delete(f"/api/v1/sessions/{session_id}")
    assert del_res.status_code == 204

    # Subsequent GET should return 404
    get_res = await client.get(f"/api/v1/sessions/{session_id}")
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_missing_session_returns_404(client: AsyncClient):
    """Verifies that deleting a non-existent session returns HTTP 404."""
    random_id = str(uuid.uuid4())
    del_res = await client.delete(f"/api/v1/sessions/{random_id}")
    assert del_res.status_code == 404


@pytest.mark.asyncio
async def test_message_persistence(client: AsyncClient):
    """Verifies that POST /api/v1/sessions/{id}/messages persists a message without faking an AI reply."""
    create_res = await client.post("/api/v1/sessions", json={"title": "Pricing Strategy Session"})
    session_id = create_res.json()["id"]

    # Post a message
    msg_payload = {
        "role": "user",
        "content": "How should an early-stage B2B founder structure annual upfront discounts?",
        "provider_metadata": {"client": "web"},
    }
    msg_res = await client.post(f"/api/v1/sessions/{session_id}/messages", json=msg_payload)
    assert msg_res.status_code == 201
    msg_data = msg_res.json()
    assert msg_data["role"] == "user"
    assert msg_data["session_id"] == session_id
    assert msg_data["content"] == msg_payload["content"]

    # Retrieve session and verify message is present
    session_res = await client.get(f"/api/v1/sessions/{session_id}")
    session_data = session_res.json()
    assert len(session_data["messages"]) == 1
    assert session_data["messages"][0]["id"] == msg_data["id"]


@pytest.mark.asyncio
async def test_message_to_missing_session_returns_404(client: AsyncClient):
    """Verifies that posting a message to a non-existent session returns HTTP 404."""
    random_id = str(uuid.uuid4())
    msg_payload = {"role": "user", "content": "Hello into the void"}
    res = await client.post(f"/api/v1/sessions/{random_id}/messages", json=msg_payload)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_message_invalid_payload_validation(client: AsyncClient):
    """Verifies that empty message content or invalid roles return HTTP 422."""
    create_res = await client.post("/api/v1/sessions", json={"title": "Validation Test"})
    session_id = create_res.json()["id"]

    # Empty content
    empty_res = await client.post(f"/api/v1/sessions/{session_id}/messages", json={"role": "user", "content": ""})
    assert empty_res.status_code == 422

    # Invalid role
    invalid_role_res = await client.post(f"/api/v1/sessions/{session_id}/messages", json={"role": "admin", "content": "Test"})
    assert invalid_role_res.status_code == 422


@pytest.mark.asyncio
async def test_session_independence_isolation(client: AsyncClient):
    """
    Guarantees strict session independence:
    Messages added to Session A must never appear in Session B.
    """
    # Create Session A
    res_a = await client.post("/api/v1/sessions", json={"title": "Session Alpha"})
    id_a = res_a.json()["id"]

    # Create Session B
    res_b = await client.post("/api/v1/sessions", json={"title": "Session Beta"})
    id_b = res_b.json()["id"]

    # Add messages to Session A
    await client.post(f"/api/v1/sessions/{id_a}/messages", json={"role": "user", "content": "Alpha Message 1"})
    await client.post(f"/api/v1/sessions/{id_a}/messages", json={"role": "assistant", "content": "Alpha Reply 1"})

    # Add message to Session B
    await client.post(f"/api/v1/sessions/{id_b}/messages", json={"role": "user", "content": "Beta Message 1"})

    # Inspect Session A
    detail_a = await client.get(f"/api/v1/sessions/{id_a}")
    messages_a = detail_a.json()["messages"]
    assert len(messages_a) == 2
    assert all("Alpha" in m["content"] for m in messages_a)

    # Inspect Session B
    detail_b = await client.get(f"/api/v1/sessions/{id_b}")
    messages_b = detail_b.json()["messages"]
    assert len(messages_b) == 1
    assert "Beta" in messages_b[0]["content"]
    assert not any("Alpha" in m["content"] for m in messages_b)


@pytest.mark.asyncio
async def test_database_connection_failure_handling(client_with_db_failure: AsyncClient):
    """
    Verifies graceful error recovery:
    When the database is unavailable, API requests return HTTP 503 rather than 500 or exposing credentials.
    """
    response = await client_with_db_failure.post("/api/v1/sessions", json={"title": "Fail Test"})
    assert response.status_code == 503
    data = response.json()
    assert data["error"] is True
    assert "unavailable" in data["message"].lower() or "failed" in data["message"].lower()


@pytest.mark.asyncio
async def test_list_session_messages(client: AsyncClient):
    """Verifies that GET /api/v1/sessions/{id}/messages returns the chronological list of messages."""
    create_res = await client.post("/api/v1/sessions", json={"title": "Message Stream Session"})
    session_id = create_res.json()["id"]

    # Initially empty
    msg_res = await client.get(f"/api/v1/sessions/{session_id}/messages")
    assert msg_res.status_code == 200
    assert msg_res.json() == []

    # Add messages
    await client.post(f"/api/v1/sessions/{session_id}/messages", json={"role": "user", "content": "Hello"})
    await client.post(f"/api/v1/sessions/{session_id}/messages", json={"role": "assistant", "content": "Hi there!"})

    # Fetch messages
    msg_res = await client.get(f"/api/v1/sessions/{session_id}/messages")
    assert msg_res.status_code == 200
    items = msg_res.json()
    assert len(items) == 2
    assert items[0]["role"] == "user"
    assert items[0]["content"] == "Hello"
    assert items[1]["role"] == "assistant"
    assert items[1]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_list_session_messages_not_found(client: AsyncClient):
    """Verifies that GET /api/v1/sessions/{invalid_id}/messages returns 404."""
    random_id = uuid.uuid4()
    response = await client.get(f"/api/v1/sessions/{random_id}/messages")
    assert response.status_code == 404


# ==============================================================================
# PATCH /sessions/{session_id} — Title Persistence Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_patch_session_title_persisted(client: AsyncClient):
    """
    Verifies that PATCH /api/v1/sessions/{id} persists a title to the database.
    After patching, a subsequent GET must return the updated title.
    """
    # Create session with the generic default title
    create_res = await client.post("/api/v1/sessions", json={"title": "New Conversation"})
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    # Derive a meaningful title from the first user message (simulates frontend flow)
    derived_title = "How do product-led growth companies build viral loops?"

    patch_res = await client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": derived_title},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == derived_title

    # Verify the title was durably persisted by fetching the session independently
    get_res = await client.get(f"/api/v1/sessions/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == derived_title


@pytest.mark.asyncio
async def test_patch_session_title_does_not_overwrite_meaningful_title(client: AsyncClient):
    """
    Verifies the protection rule: a meaningful user-defined title must not be
    overwritten by a PATCH request that sends the generic 'New Conversation'
    placeholder (guards against accidental regressions).
    """
    # Create session with a meaningful title already
    create_res = await client.post("/api/v1/sessions", json={"title": "Retention loops for B2B SaaS"})
    session_id = create_res.json()["id"]
    original_title = create_res.json()["title"]

    # Attempt to overwrite with the generic placeholder
    patch_res = await client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": "New Conversation"},
    )
    assert patch_res.status_code == 200
    # The backend should reject the downgrade and keep the original meaningful title
    assert patch_res.json()["title"] == original_title

    # Verify persisted title was not clobbered
    get_res = await client.get(f"/api/v1/sessions/{session_id}")
    assert get_res.json()["title"] == original_title


@pytest.mark.asyncio
async def test_patch_session_unknown_id_returns_404(client: AsyncClient):
    """
    Verifies that PATCH /api/v1/sessions/{unknown_id} returns 404
    for a session UUID that does not exist in the database.
    """
    unknown_id = str(uuid.uuid4())
    patch_res = await client.patch(
        f"/api/v1/sessions/{unknown_id}",
        json={"title": "Ghost Session Title"},
    )
    assert patch_res.status_code == 404
    data = patch_res.json()
    assert data["error"] is True
    assert "not found" in data["message"].lower()


@pytest.mark.asyncio
async def test_existing_chat_flow_title_handling_compatible(client: AsyncClient):
    """
    Regression test: verifies that the standard session create → message post
    → PATCH title flow works end-to-end without breaking existing behaviour.
    Chat generation does NOT need the PATCH to succeed for messages to persist.
    """
    # Create a new session (frontend always starts with 'New Conversation')
    create_res = await client.post(
        "/api/v1/sessions",
        json={"title": "New Conversation", "provider": "ollama"},
    )
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]
    assert create_res.json()["title"] == "New Conversation"

    # Simulate storing the first user message (happens inside the chat endpoint)
    msg_res = await client.post(
        f"/api/v1/sessions/{session_id}/messages",
        json={"role": "user", "content": "What is activation in product-led growth?"},
    )
    assert msg_res.status_code == 201

    # Frontend derives the title and calls the PATCH endpoint
    derived_title = "What is activation in product-led grow..."
    patch_res = await client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"title": derived_title},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == derived_title

    # Messages are intact and session title is updated
    get_res = await client.get(f"/api/v1/sessions/{session_id}")
    assert get_res.json()["title"] == derived_title
    assert len(get_res.json()["messages"]) == 1

