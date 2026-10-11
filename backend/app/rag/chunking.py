"""
Podcast transcript chunking strategies for the RAG pipeline.
Synchronized with ingestion.chunker for consistent dialogue-aware segmentation.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ingestion.parser import ParsedSpeakerTurn, TranscriptMetadata
from ingestion.chunker import TranscriptChunkData, TranscriptChunker as IngestionTranscriptChunker


@dataclass
class TranscriptTurn:
    """Represents a speaker turn in RAG pipelines."""
    speaker: str
    timestamp_start: str
    timestamp_end: str
    text: str
    start_seconds: int = 0
    end_seconds: int = 0

    def to_parsed_turn(self) -> ParsedSpeakerTurn:
        return ParsedSpeakerTurn(
            speaker=self.speaker,
            timestamp_start=self.timestamp_start,
            timestamp_end=self.timestamp_end,
            start_seconds=self.start_seconds,
            end_seconds=self.end_seconds,
            text=self.text,
        )


# ChunkResult alias pointing to the unified TranscriptChunkData
ChunkResult = TranscriptChunkData


class TranscriptChunker:
    """
    RAG chunking wrapper delegating to IngestionTranscriptChunker.
    Preserves speaker turns, timestamp bounds, and contextual overlap.
    """

    def __init__(self, target_chunk_size: int = 500, overlap_size: int = 100):
        self.chunker = IngestionTranscriptChunker(
            target_chunk_size=target_chunk_size,
            overlap_size=overlap_size,
        )

    def chunk_turns(
        self,
        turns: List[TranscriptTurn],
        episode_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ChunkResult]:
        """
        Groups transcript turns into semantic chunks with sliding overlap.
        """
        meta_dict = episode_metadata or {}
        metadata = TranscriptMetadata(
            episode_id=meta_dict.get("episode_id", "episode"),
            title=meta_dict.get("episode_title", meta_dict.get("title", "Episode")),
            guest=meta_dict.get("guest_name", meta_dict.get("guest", "Guest")),
            youtube_url=meta_dict.get("youtube_url"),
            video_id=meta_dict.get("video_id"),
        )
        parsed_turns = [t.to_parsed_turn() for t in turns]
        return self.chunker.chunk_turns(turns=parsed_turns, metadata=metadata)
