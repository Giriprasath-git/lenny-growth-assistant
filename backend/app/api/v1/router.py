"""
Main API v1 router consolidating endpoints.
"""

from fastapi import APIRouter
from backend.app.api.v1.endpoints import artifacts, chat, essays, health, sessions, transcripts

api_v1_router = APIRouter(prefix="/v1")

# Mount endpoint modules
api_v1_router.include_router(health.router, tags=["Health & Diagnostics"])
api_v1_router.include_router(sessions.router, prefix="/sessions", tags=["Sessions & Messages"])
api_v1_router.include_router(chat.router, prefix="/chat", tags=["Chat & Streaming"])
api_v1_router.include_router(transcripts.router, prefix="/transcripts", tags=["Transcripts & RAG"])
api_v1_router.include_router(essays.router, prefix="/essays", tags=["Ship 30 Essays"])
api_v1_router.include_router(artifacts.router, prefix="/artifacts", tags=["Artifacts & Deliverables"])

