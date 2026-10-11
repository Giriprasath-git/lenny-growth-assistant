"""
Transcript database ingestion engine for The Lenny Growth Assistant.
Persists parsed, speaker-aware chunks to PostgreSQL transcript_chunks table.
Implements bounded batching, content hashing, idempotent deduplication, and transaction rollback.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.models.message import MessageCitation
from backend.app.db.models.transcript import TranscriptChunk
from ingestion.chunker import TranscriptChunkData, TranscriptChunker
from ingestion.parser import ParsedTranscript, TranscriptParser


@dataclass
class EpisodeIngestionResult:
    """Individual status for an episode ingestion attempt."""
    episode_id: str
    title: str
    guest: str
    chunks_count: int
    status: str  # "inserted", "updated", "skipped", "failed", "conflict"
    error_message: Optional[str] = None


@dataclass
class IngestionReport:
    """Consolidated summary report of an ingestion run."""
    total_files_discovered: int = 0
    episodes_processed: int = 0
    episodes_inserted: int = 0
    episodes_updated: int = 0
    episodes_skipped: int = 0
    episodes_conflicted: int = 0
    episodes_failed: int = 0
    total_chunks_stored: int = 0
    results: List[EpisodeIngestionResult] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files_discovered": self.total_files_discovered,
            "episodes_processed": self.episodes_processed,
            "episodes_inserted": self.episodes_inserted,
            "episodes_updated": self.episodes_updated,
            "episodes_skipped": self.episodes_skipped,
            "episodes_conflicted": self.episodes_conflicted,
            "episodes_failed": self.episodes_failed,
            "total_chunks_stored": self.total_chunks_stored,
            "duration_seconds": round(self.duration_seconds, 2),
            "errors_count": len(self.errors),
        }


class TranscriptIndexer:
    """
    Manages bounded batch ingestion into PostgreSQL transcript_chunks table.
    Enforces idempotency, detects duplicate content, updates modified transcripts,
    safeguards historical citations against destructive replacement, and protects
    database consistency with transactional rollbacks.
    """

    def __init__(
        self,
        chunk_batch_size: int = 50,
        chunker: Optional[TranscriptChunker] = None,
    ):
        self.chunk_batch_size = max(1, min(chunk_batch_size, 200))
        self.chunker = chunker or TranscriptChunker()

    async def ingest_episode(
        self,
        transcript: ParsedTranscript,
        db: AsyncSession,
    ) -> EpisodeIngestionResult:
        """
        Ingests a single ParsedTranscript into the transcript_chunks table.
        Idempotent:
        - If episode already exists with identical content hash, skips insertion.
        - If episode exists with different content hash:
          * If chunks are cited by historical chat sessions, permanently blocks destructive
            replacement, logs conflict, and preserves existing chunks and citations.
          * Otherwise, removes outdated chunks and inserts updated chunks.
        - If episode is new, inserts chunks in bounded batches.
        Wraps operations in a savepoint/transaction with rollback on failure.
        """
        ep_meta = transcript.metadata
        episode_id = ep_meta.episode_id

        try:
            # Step 1: Check existing record for this episode_id
            existing_query = (
                select(TranscriptChunk.id, TranscriptChunk.metadata_json)
                .where(TranscriptChunk.episode_id == episode_id)
                .limit(1)
            )
            existing_result = await db.execute(existing_query)
            existing_row = existing_result.first()

            if existing_row:
                # Compare stored episode content hash
                stored_meta = existing_row.metadata_json or {}
                stored_hash = stored_meta.get("episode_content_hash", "")

                if stored_hash and stored_hash == ep_meta.raw_content_hash:
                    # Content is strictly identical, skip re-ingestion
                    count_query = select(func.count(TranscriptChunk.id)).where(
                        TranscriptChunk.episode_id == episode_id
                    )
                    count_res = await db.execute(count_query)
                    chunk_count = count_res.scalar_one_or_none() or 0

                    logger.info(f"Skipping unchanged episode '{episode_id}' (hash match, {chunk_count} chunks)")
                    return EpisodeIngestionResult(
                        episode_id=episode_id,
                        title=ep_meta.title,
                        guest=ep_meta.guest,
                        chunks_count=chunk_count,
                        status="skipped",
                    )

                # Content changed: verify whether existing chunks are cited by historical messages
                citation_check = (
                    select(func.count(MessageCitation.id))
                    .join(TranscriptChunk, MessageCitation.chunk_id == TranscriptChunk.id)
                    .where(TranscriptChunk.episode_id == episode_id)
                )
                cited_count = (await db.execute(citation_check)).scalar_one_or_none() or 0

                if cited_count > 0:
                    count_query = select(func.count(TranscriptChunk.id)).where(
                        TranscriptChunk.episode_id == episode_id
                    )
                    existing_chunk_count = (await db.execute(count_query)).scalar_one_or_none() or 0

                    warning_msg = (
                        f"Citation Integrity Conflict: Episode '{episode_id}' has modified content, "
                        f"but {cited_count} chunk(s) are actively referenced by historical chat citations. "
                        f"Destructive chunk replacement is permanently blocked to prevent corruption of historical citations. "
                        f"Existing chunks and citations have been preserved."
                    )
                    logger.warning(warning_msg)
                    return EpisodeIngestionResult(
                        episode_id=episode_id,
                        title=ep_meta.title,
                        guest=ep_meta.guest,
                        chunks_count=existing_chunk_count,
                        status="conflict",
                        error_message=warning_msg,
                    )

                # Safe to update: no historical citations attach to this episode's chunks
                logger.info(f"Updating modified episode '{episode_id}' (hash mismatch, 0 active citations)")
                delete_stmt = delete(TranscriptChunk).where(TranscriptChunk.episode_id == episode_id)
                await db.execute(delete_stmt)
                action_status = "updated"
            else:
                action_status = "inserted"

            # Step 2: Chunk the transcript
            chunk_data_list = self.chunker.chunk_transcript(transcript)
            if not chunk_data_list:
                logger.warning(f"No valid chunks generated for episode '{episode_id}'")
                return EpisodeIngestionResult(
                    episode_id=episode_id,
                    title=ep_meta.title,
                    guest=ep_meta.guest,
                    chunks_count=0,
                    status="skipped",
                )

            # Step 3: Insert chunks in bounded batches
            total_chunks = len(chunk_data_list)
            for batch_start in range(0, total_chunks, self.chunk_batch_size):
                batch = chunk_data_list[batch_start : batch_start + self.chunk_batch_size]
                models = [
                    TranscriptChunk(
                        id=c.id,
                        episode_id=c.episode_id,
                        episode_title=c.episode_title,
                        guest_name=c.guest_name,
                        timestamp_start=c.timestamp_start,
                        timestamp_end=c.timestamp_end,
                        chunk_index=c.chunk_index,
                        content=c.content,
                        metadata_json=c.metadata_json,
                    )
                    for c in batch
                ]
                db.add_all(models)
                await db.flush()

            # Commit current episode changes
            await db.commit()

            logger.info(f"Successfully {action_status} episode '{episode_id}' with {total_chunks} chunks")
            return EpisodeIngestionResult(
                episode_id=episode_id,
                title=ep_meta.title,
                guest=ep_meta.guest,
                chunks_count=total_chunks,
                status=action_status,
            )

        except Exception as e:
            # Safeguard rollback on error
            await db.rollback()
            logger.error(f"Failed to ingest episode '{episode_id}': {e}", exc_info=True)
            return EpisodeIngestionResult(
                episode_id=episode_id,
                title=ep_meta.title,
                guest=ep_meta.guest,
                chunks_count=0,
                status="failed",
                error_message=str(e),
            )

    async def ingest_directory(
        self,
        root_dir: Path,
        db: AsyncSession,
        dataset_root: Optional[Path] = None,
        limit: Optional[int] = None,
    ) -> IngestionReport:
        """
        Discovers and ingests all transcript Markdown files in root_dir.
        Optionally parses index/ topic catalogs if present in dataset_root.
        """
        start_time = time.time()
        report = IngestionReport()

        actual_dataset_root = dataset_root or root_dir
        index_dir = actual_dataset_root / "index"
        topic_index: Dict[str, List[str]] = {}
        if index_dir.exists():
            topic_index = TranscriptParser.parse_topic_indexes(index_dir)
            logger.info(f"Loaded supplemental topic tags for {len(topic_index)} episode slugs")

        files = TranscriptParser.discover_transcript_files(root_dir)
        report.total_files_discovered = len(files)

        if limit and limit > 0:
            files = files[:limit]

        for file_path in files:
            try:
                parsed = TranscriptParser.parse_file(
                    file_path=file_path,
                    dataset_root=actual_dataset_root,
                    topic_index=topic_index,
                )
                if not parsed:
                    report.episodes_failed += 1
                    report.errors.append({
                        "file": str(file_path),
                        "error": "Failed to parse transcript or empty file",
                    })
                    continue

                res = await self.ingest_episode(parsed, db)
                report.episodes_processed += 1
                report.results.append(res)

                if res.status == "inserted":
                    report.episodes_inserted += 1
                    report.total_chunks_stored += res.chunks_count
                elif res.status == "updated":
                    report.episodes_updated += 1
                    report.total_chunks_stored += res.chunks_count
                elif res.status == "skipped":
                    report.episodes_skipped += 1
                elif res.status == "conflict":
                    report.episodes_conflicted += 1
                    report.errors.append({
                        "file": str(file_path),
                        "episode_id": res.episode_id,
                        "error": res.error_message,
                        "type": "citation_conflict",
                    })
                elif res.status == "failed":
                    report.episodes_failed += 1
                    report.errors.append({
                        "file": str(file_path),
                        "episode_id": res.episode_id,
                        "error": res.error_message,
                    })

            except Exception as e:
                report.episodes_failed += 1
                report.errors.append({"file": str(file_path), "error": str(e)})

        report.duration_seconds = time.time() - start_time
        return report

    async def index_episode_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Compatibility method for early Phase 1/2 callers."""
        return len(chunks)
