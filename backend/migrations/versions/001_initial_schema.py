"""Initial PostgreSQL database schema for The Lenny Growth Assistant.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-10-09 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. PostgreSQL Extensions
    # Modern PostgreSQL (13+) includes built-in gen_random_uuid() natively without extensions.
    # Safe fallback to uuid-ossp if gen_random_uuid() is absent on legacy instances.
    # NOTE: The pgvector extension ("vector") is intentionally deferred to Phase 3 (RAG & Ingestion)
    # to allow Phase 2 session persistence to initialize cleanly without pgvector dependencies.
    op.execute("""
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)

    # 1. Chat Sessions Table
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New Conversation"),
        sa.Column("user_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="cloud"),
        sa.Column("model_name", sa.String(length=100), nullable=False, server_default="claude-3-5-sonnet-20241022"),
        sa.Column("active_skill", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_sessions_id", "chat_sessions", ["id"])
    op.create_index("ix_chat_sessions_created_at_desc", "chat_sessions", ["created_at"])
    op.create_index("ix_chat_sessions_updated_at_desc", "chat_sessions", ["updated_at"])

    # 2. Transcript Chunks Table (Metadata-only in Phase 2; vector embeddings deferred to Phase 3)
    op.create_table(
        "transcript_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("episode_id", sa.String(length=100), nullable=False),
        sa.Column("episode_title", sa.String(length=255), nullable=False),
        sa.Column("guest_name", sa.String(length=255), nullable=False),
        sa.Column("timestamp_start", sa.String(length=20), nullable=False),
        sa.Column("timestamp_end", sa.String(length=20), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_transcript_chunks_id", "transcript_chunks", ["id"])
    op.create_index("ix_transcript_chunks_episode_id", "transcript_chunks", ["episode_id"])
    op.create_index("ix_transcript_chunks_guest_name", "transcript_chunks", ["guest_name"])

    # 3. Chat Messages Table
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provider_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_chat_messages_role"),
    )
    op.create_index("ix_chat_messages_id", "chat_messages", ["id"])
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_index("ix_chat_messages_session_id_created_at", "chat_messages", ["session_id", "created_at"])

    # 4. Message Citations Table
    op.create_table(
        "message_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transcript_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("citation_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("episode_id", sa.String(length=100), nullable=True),
        sa.Column("episode_title", sa.String(length=255), nullable=True),
        sa.Column("guest_name", sa.String(length=255), nullable=True),
        sa.Column("timestamp_start", sa.String(length=20), nullable=True),
        sa.Column("timestamp_end", sa.String(length=20), nullable=True),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
    )
    op.create_index("ix_message_citations_id", "message_citations", ["id"])
    op.create_index("ix_message_citations_message_id", "message_citations", ["message_id"])
    op.create_index("ix_message_citations_message_id_citation_index", "message_citations", ["message_id", "citation_index"])

    # 5. Artifacts Table
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_artifacts_id", "artifacts", ["id"])
    op.create_index("ix_artifacts_session_id", "artifacts", ["session_id"])


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("message_citations")
    op.drop_table("chat_messages")
    op.drop_table("transcript_chunks")
    op.drop_table("chat_sessions")
