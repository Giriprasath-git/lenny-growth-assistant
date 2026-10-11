"""
Integration tests for database ingestion pipeline in ingestion/indexer.py.
Validates batch storage, idempotency, duplicate prevention, update handling, and transaction rollback.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.transcript import TranscriptChunk
from ingestion.indexer import TranscriptIndexer
from ingestion.parser import TranscriptParser


@pytest.mark.asyncio
async def test_single_episode_ingestion(ingestion_db_session: AsyncSession, synthetic_valid_markdown: str):
    parsed = TranscriptParser.parse_text(synthetic_valid_markdown)
    indexer = TranscriptIndexer(chunk_batch_size=10)

    # First ingestion: should insert
    res = await indexer.ingest_episode(parsed, ingestion_db_session)
    assert res.status == "inserted"
    assert res.chunks_count > 0

    # Verify rows in database
    query = select(TranscriptChunk).where(TranscriptChunk.episode_id == parsed.metadata.episode_id)
    result = await ingestion_db_session.execute(query)
    stored_chunks = result.scalars().all()
    assert len(stored_chunks) == res.chunks_count

    first_chunk = stored_chunks[0]
    assert first_chunk.guest_name == "Alice Engineer"
    assert first_chunk.metadata_json["video_id"] == "dQw4w9WgXcQ"
    assert "youtube_timestamp_url" in first_chunk.metadata_json


@pytest.mark.asyncio
async def test_idempotent_reingestion_skips_unchanged(
    ingestion_db_session: AsyncSession, synthetic_valid_markdown: str
):
    parsed = TranscriptParser.parse_text(synthetic_valid_markdown)
    indexer = TranscriptIndexer(chunk_batch_size=10)

    # Initial ingestion
    res1 = await indexer.ingest_episode(parsed, ingestion_db_session)
    assert res1.status == "inserted"

    # Re-ingest exact same content: should skip
    res2 = await indexer.ingest_episode(parsed, ingestion_db_session)
    assert res2.status == "skipped"
    assert res2.chunks_count == res1.chunks_count

    # Total rows in DB should NOT double
    count_query = select(func.count(TranscriptChunk.id)).where(
        TranscriptChunk.episode_id == parsed.metadata.episode_id
    )
    total_in_db = (await ingestion_db_session.execute(count_query)).scalar_one()
    assert total_in_db == res1.chunks_count


@pytest.mark.asyncio
async def test_updating_modified_transcript(
    ingestion_db_session: AsyncSession, synthetic_valid_markdown: str
):
    parsed1 = TranscriptParser.parse_text(synthetic_valid_markdown)
    indexer = TranscriptIndexer(chunk_batch_size=10)

    # Ingest original
    res1 = await indexer.ingest_episode(parsed1, ingestion_db_session)
    assert res1.status == "inserted"

    # Modify transcript content (e.g. adding a new dialogue line)
    modified_md = synthetic_valid_markdown + "\n\nLenny (00:06:00):\nOne final question on scaling teams."
    parsed2 = TranscriptParser.parse_text(modified_md)

    # Re-ingest modified: should update and replace old chunks
    res2 = await indexer.ingest_episode(parsed2, ingestion_db_session)
    assert res2.status == "updated"

    # Verify rows in DB match new chunks count, not sum of both
    count_query = select(func.count(TranscriptChunk.id)).where(
        TranscriptChunk.episode_id == parsed2.metadata.episode_id
    )
    total_in_db = (await ingestion_db_session.execute(count_query)).scalar_one()
    assert total_in_db == res2.chunks_count


@pytest.mark.asyncio
async def test_transaction_rollback_on_failure(
    ingestion_db_session: AsyncSession, synthetic_valid_markdown: str
):
    parsed = TranscriptParser.parse_text(synthetic_valid_markdown)
    indexer = TranscriptIndexer(chunk_batch_size=10)

    # Simulate database flush error during batch insertion
    with patch.object(ingestion_db_session, "flush", side_effect=RuntimeError("Simulated DB connection drop")):
        res = await indexer.ingest_episode(parsed, ingestion_db_session)
        assert res.status == "failed"
        assert "Simulated DB connection drop" in (res.error_message or "")

    # Ensure no orphan rows were committed to DB
    count_query = select(func.count(TranscriptChunk.id)).where(
        TranscriptChunk.episode_id == parsed.metadata.episode_id
    )
    total_in_db = (await ingestion_db_session.execute(count_query)).scalar_one()
    assert total_in_db == 0


@pytest.mark.asyncio
async def test_ingest_directory_summary_report(
    ingestion_db_session: AsyncSession, synthetic_dataset_dir: Path
):
    indexer = TranscriptIndexer(chunk_batch_size=10)

    report = await indexer.ingest_directory(
        root_dir=synthetic_dataset_dir,
        db=ingestion_db_session,
        dataset_root=synthetic_dataset_dir,
    )

    assert report.total_files_discovered == 2
    assert report.episodes_processed == 2
    assert report.episodes_inserted == 2
    assert report.episodes_failed == 0
    assert report.total_chunks_stored > 0

    # Running ingest_directory again should result in all skipped
    second_report = await indexer.ingest_directory(
        root_dir=synthetic_dataset_dir,
        db=ingestion_db_session,
        dataset_root=synthetic_dataset_dir,
    )
    assert second_report.episodes_skipped == 2
    assert second_report.episodes_inserted == 0


@pytest.mark.asyncio
async def test_reingestion_preserves_cited_chunks_conflict_policy(
    ingestion_db_session: AsyncSession, synthetic_valid_markdown: str
):
    """
    Validates citation integrity:
    When an episode is modified (content hash changes) but its chunks are already
    referenced by historical chat citations (MessageCitation), re-ingestion MUST NOT
    destructively delete or replace those chunks.
    It must permanently reject the destructive update, return status="conflict",
    and leave existing chunks, hashes, and citation references intact with zero partial modifications.
    Any attempt to pass removed unsafe flags must fail.
    """
    import uuid
    from backend.app.db.models.session import ChatSession
    from backend.app.db.models.message import ChatMessage, MessageCitation

    # 1. Ingest initial episode
    parsed1 = TranscriptParser.parse_text(synthetic_valid_markdown)
    indexer = TranscriptIndexer(chunk_batch_size=10)
    res1 = await indexer.ingest_episode(parsed1, ingestion_db_session)
    assert res1.status == "inserted"

    # 2. Retrieve one stored chunk from database and record total count
    stmt = select(TranscriptChunk).where(TranscriptChunk.episode_id == parsed1.metadata.episode_id)
    chunk_res = await ingestion_db_session.execute(stmt)
    chunks = chunk_res.scalars().all()
    initial_chunk_count = len(chunks)
    assert initial_chunk_count > 0
    target_chunk = chunks[0]
    target_chunk_id = target_chunk.id

    # 3. Simulate a chat session where an assistant response cited this chunk
    session = ChatSession(id=uuid.uuid4(), title="Test Conversation")
    ingestion_db_session.add(session)
    await ingestion_db_session.flush()

    msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="assistant",
        content="According to Alice, decoupling is the primary signal for scale.",
    )
    ingestion_db_session.add(msg)
    await ingestion_db_session.flush()

    citation = MessageCitation(
        id=uuid.uuid4(),
        message_id=msg.id,
        chunk_id=target_chunk_id,
        citation_index=1,
        episode_id=target_chunk.episode_id,
        episode_title=target_chunk.episode_title,
        guest_name=target_chunk.guest_name,
        timestamp_start=target_chunk.timestamp_start,
        timestamp_end=target_chunk.timestamp_end,
        quoted_text="The primary signal is decoupling.",
    )
    ingestion_db_session.add(citation)
    await ingestion_db_session.commit()

    # 4. Modify transcript content so content hash changes
    modified_md = synthetic_valid_markdown + "\n\nLenny (00:07:00):\nAdditional follow up questions."
    parsed2 = TranscriptParser.parse_text(modified_md)
    assert parsed2.metadata.episode_id == parsed1.metadata.episode_id
    assert parsed2.metadata.raw_content_hash != parsed1.metadata.raw_content_hash

    # 5. Attempt re-ingestion: must permanently reject destructive replacement
    res_conflict = await indexer.ingest_episode(parsed2, ingestion_db_session)

    # Must report conflict and NOT delete/replace chunks
    assert res_conflict.status == "conflict"
    assert "citations" in (res_conflict.error_message or "").lower()
    assert res_conflict.chunks_count == initial_chunk_count

    # 6. Verify database is completely unmodified (zero partial writes, zero deleted chunks)
    verify_chunk = await ingestion_db_session.get(TranscriptChunk, target_chunk_id)
    assert verify_chunk is not None
    assert verify_chunk.metadata_json["episode_content_hash"] == parsed1.metadata.raw_content_hash

    # Verify citation still firmly references target_chunk_id (not NULLified)
    verify_citation = await ingestion_db_session.get(MessageCitation, citation.id)
    assert verify_citation is not None
    assert verify_citation.chunk_id == target_chunk_id

    # Verify total chunk count in DB for this episode is unchanged
    count_query = select(func.count(TranscriptChunk.id)).where(
        TranscriptChunk.episode_id == parsed1.metadata.episode_id
    )
    total_in_db = (await ingestion_db_session.execute(count_query)).scalar_one()
    assert total_in_db == initial_chunk_count

    # 7. Verify repeated re-ingestion attempts consistently reject destructive updates
    res_conflict_2 = await indexer.ingest_episode(parsed2, ingestion_db_session)
    assert res_conflict_2.status == "conflict"

    # 8. Verify unsafe allow_cited_updates argument is completely removed from TranscriptIndexer API
    with pytest.raises(TypeError):
        TranscriptIndexer(allow_cited_updates=True)  # type: ignore

