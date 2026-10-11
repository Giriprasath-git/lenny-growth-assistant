"""
CLI ingestion runner for The Lenny Growth Assistant.
Manual entrypoint for ingesting downloaded podcast transcripts into PostgreSQL.
NOTE: Do NOT run automatically during agent turns. Run manually by user when dataset is present.

Usage:
    python ingestion/run_ingestion.py --data-dir data/raw_transcripts
    python ingestion/run_ingestion.py --data-dir data/raw_transcripts --dry-run
    python ingestion/run_ingestion.py --limit 5
"""

import argparse
import asyncio
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import settings
from backend.app.core.logging import logger, setup_logging
from backend.app.db.session import AsyncSessionLocal
from ingestion.indexer import TranscriptIndexer
from ingestion.parser import TranscriptParser


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Lenny's Podcast transcripts into PostgreSQL.")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(PROJECT_ROOT / "data" / "raw_transcripts"),
        help="Path to the raw transcripts directory (e.g. data/raw_transcripts)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of episodes to process (useful for testing)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Chunk batch insertion size",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to database",
    )

    args = parser.parse_args()
    data_path = Path(args.data_dir).resolve()

    logger.info(f"Starting transcript ingestion from: {data_path}")
    logger.info(f"Dry run: {args.dry_run}, Limit: {args.limit}")

    if not data_path.exists():
        logger.error(f"Data directory not found: {data_path}")
        logger.error("Please download the ChatPRD dataset into data/raw_transcripts before running.")
        sys.exit(1)

    files = TranscriptParser.discover_transcript_files(data_path)
    logger.info(f"Discovered {len(files)} transcript files.")

    if not files:
        logger.warning("No transcript markdown files found. Ensure dataset is placed in the target directory.")
        return

    if args.dry_run:
        logger.info("Executing dry-run parse validation...")
        parsed_count = 0
        total_chunks = 0
        from ingestion.chunker import TranscriptChunker
        chunker = TranscriptChunker()

        target_files = files[: args.limit] if args.limit else files
        for f in target_files:
            parsed = TranscriptParser.parse_file(f, dataset_root=data_path)
            if parsed:
                chunks = chunker.chunk_transcript(parsed)
                parsed_count += 1
                total_chunks += len(chunks)
                logger.info(
                    f"Parsed: '{parsed.metadata.title}' by {parsed.metadata.guest} "
                    f"({len(parsed.turns)} turns, {len(chunks)} chunks, ID: {parsed.metadata.episode_id})"
                )

        logger.info(f"Dry run complete. Validated {parsed_count} episodes, generated {total_chunks} chunks.")
        return

    indexer = TranscriptIndexer(
        chunk_batch_size=args.batch_size,
    )

    async with AsyncSessionLocal() as session:
        report = await indexer.ingest_directory(
            root_dir=data_path,
            db=session,
            dataset_root=data_path,
            limit=args.limit,
        )

    logger.info("==================================================")
    logger.info("INGESTION SUMMARY REPORT")
    logger.info("==================================================")
    logger.info(f"Total files discovered : {report.total_files_discovered}")
    logger.info(f"Episodes processed     : {report.episodes_processed}")
    logger.info(f"Episodes inserted      : {report.episodes_inserted}")
    logger.info(f"Episodes updated       : {report.episodes_updated}")
    logger.info(f"Episodes skipped       : {report.episodes_skipped}")
    logger.info(f"Episodes conflicted    : {report.episodes_conflicted}")
    logger.info(f"Episodes failed        : {report.episodes_failed}")
    logger.info(f"Total chunks stored    : {report.total_chunks_stored}")
    logger.info(f"Duration               : {report.duration_seconds:.2f} seconds")
    if report.errors:
        logger.warning(f"Errors encountered ({len(report.errors)}):")
        for err in report.errors:
            logger.warning(f"  - {err}")
    logger.info("==================================================")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
