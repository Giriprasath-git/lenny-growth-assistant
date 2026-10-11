"""
Chat and Conversational AI Agent REST API endpoints under /api/v1/chat.
Implements grounded Q&A execution, model provider dispatch, and citation generation.
"""

from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.engine import AgentEngine
from backend.app.agent.providers.gemini import GeminiProvider
from backend.app.core.config import settings
from backend.app.core.exceptions import AppException, ProviderUnavailableError, SessionNotFoundError
from backend.app.core.logging import logger
from backend.app.db.session import get_db
from backend.app.schemas.chat import ChatTurnRequest, ChatTurnResponse

router = APIRouter()

# Reusable AgentEngine instance
agent_engine = AgentEngine()


@router.post(
    "",
    response_model=ChatTurnResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute grounded AI conversation turn",
    description=(
        "Retrieves relevant transcript chunks from Lenny's podcast archives, constructs "
        "injection-safe context, invokes the configured model provider (local Ollama default "
        "or cloud Gemini free-tier), and persists the turn with source citations."
    ),
)
async def chat_turn(
    payload: ChatTurnRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatTurnResponse:
    """Executes a single conversational turn with grounded transcript citations."""
    try:
        response = await agent_engine.execute_turn(
            session_id=payload.session_id,
            user_message=payload.message,
            db=db,
            provider=payload.provider,
            model=payload.model,
            active_skill=payload.active_skill,
            top_k=payload.top_k,
        )
        return response
    except (SessionNotFoundError, ProviderUnavailableError) as domain_err:
        # These are handled cleanly by the global AppException handler in main.py
        raise domain_err
    except Exception as e:
        logger.exception("Unexpected error during agent chat execution: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat execution failed: {str(e)}",
        )


@router.post(
    "/message",
    response_model=ChatTurnResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute grounded chat turn (alias endpoint)",
    description="Compatible alias for POST /api/v1/chat.",
)
async def chat_message_alias(
    payload: ChatTurnRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatTurnResponse:
    """Alias endpoint routing to standard turn execution."""
    return await chat_turn(payload=payload, db=db)


@router.post(
    "/agent",
    response_model=ChatTurnResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute grounded AI turn using Pi Coding Agent SDK",
    description=(
        "Executes a conversation turn backed by the real @earendil-works/pi-coding-agent SDK bridge "
        "running against local Ollama (qwen2.5:1.5b). Enforces empty-tool security restrictions and "
        "persists turns and citations to PostgreSQL."
    ),
)
async def chat_agent_turn(
    payload: ChatTurnRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatTurnResponse:
    """Executes a conversation turn explicitly routed to the Pi Coding Agent SDK."""
    req_provider = payload.provider or "pi_agent"
    try:
        response = await agent_engine.execute_turn(
            session_id=payload.session_id,
            user_message=payload.message,
            db=db,
            provider=req_provider,
            model=payload.model or settings.PI_AGENT_MODEL,
            active_skill=payload.active_skill,
            top_k=payload.top_k,
        )
        return response
    except (SessionNotFoundError, ProviderUnavailableError) as domain_err:
        raise domain_err
    except Exception as e:
        logger.exception("Unexpected error during Pi Coding Agent SDK execution: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent SDK execution failed: {str(e)}",
        )


@router.post(
    "/essay",
    status_code=status.HTTP_200_OK,
    summary="Generate Ship 30 essay via chat router (alias)",
    description="Compatible alias for POST /api/v1/essays.",
)
async def chat_essay_alias(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Alias endpoint for Ship 30 essay generation under the chat router."""
    from backend.app.schemas.essay import EssayGenerateRequest
    from backend.app.agent.essay_service import EssayGenerationService
    service = EssayGenerationService()
    req = EssayGenerateRequest.model_validate(payload)
    res = await service.generate_essay(payload=req, db=db)
    return res.model_dump()


@router.get(
    "/sdk-status",
    summary="Get coding-agent SDK compatibility and model provider status",
    description="Returns live audit status for Claude Agent SDK, Pi Coding Agent, and active providers.",
)
async def get_sdk_status() -> Dict[str, Any]:
    """Returns audit and health status regarding coding-agent SDKs and model providers."""
    gemini_provider = GeminiProvider()
    gemini_health = await gemini_provider.check_health()

    from backend.app.agent.providers.pi_agent import PiAgentProvider
    pi_provider = PiAgentProvider()
    pi_health = await pi_provider.check_health()

    return {
        "active_default_provider": settings.DEFAULT_LLM_PROVIDER,
        "ollama_configuration": {
            "endpoint": settings.OLLAMA_BASE_URL,
            "model": settings.OLLAMA_MODEL,
            "timeout_seconds": settings.OLLAMA_REQUEST_TIMEOUT,
            "max_tokens": settings.OLLAMA_NUM_PREDICT,
            "temperature": settings.OLLAMA_TEMPERATURE,
            "mode": "local_offline_http",
        },
        "cloud_configuration": {
            "backend": "gemini",
            "provider": "cloud",
            "model": settings.GEMINI_MODEL,
            "status": gemini_health["status"],
            "configured": gemini_health["configured"],
            "verified": gemini_health.get("verified", False),
            "free_tier_eligible": True,
            "free_tier_note": (
                "gemini-3.5-flash-lite is documented with free-tier text generation availability in Google AI Studio. "
                "Quotas, rate limits, and regional availability must be verified in user's Google AI Studio console."
            ),
            "is_optional": True,
            "notice": (
                "A GEMINI_API_KEY is required only for live cloud verification. "
                "Local Ollama mode is fully active and does not require credentials."
            ) if not gemini_health["configured"] else None,
        },
        "legacy_cloud_configuration": {
            "backend": "anthropic",
            "configured": bool(settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY.strip()),
            "model": settings.ANTHROPIC_MODEL,
            "is_optional": True,
        },
        "coding_agent_sdks": {
            "claude_agent_sdk": agent_engine.claude_sdk_boundary.get_audit_summary(),
            "pi_coding_agent": {
                **agent_engine.pi_sdk_boundary.get_audit_summary(),
                "service_health": pi_health,
            },
        },
    }
