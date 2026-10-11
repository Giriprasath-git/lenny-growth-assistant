"""
Podcast transcript chunking engine for The Lenny Growth Assistant.
Produces deterministic, retrieval-friendly chunks preserving speaker continuity,
timestamp bounds, and YouTube citation URLs.
"""

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, List, Optional, Set
import uuid
from backend.app.core.config import settings
from backend.app.core.logging import logger
from ingestion.parser import (
    ParsedSpeakerTurn,
    ParsedTranscript,
    TranscriptMetadata,
    build_youtube_timestamp_url,
    format_seconds_to_timestamp,
)


@dataclass
class TranscriptChunkData:
    """
    Representation of a processed transcript chunk ready for PostgreSQL persistence.
    Directly aligns with backend.app.db.models.transcript.TranscriptChunk.
    """
    id: uuid.UUID
    episode_id: str
    episode_title: str
    guest_name: str
    timestamp_start: str
    timestamp_end: str
    chunk_index: int
    content: str
    metadata_json: Dict[str, Any] = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(self.content.split())

    def to_dict(self) -> Dict[str, Any]:
        """Converts chunk data to dictionary for ORM model instantiation."""
        return {
            "id": self.id,
            "episode_id": self.episode_id,
            "episode_title": self.episode_title,
            "guest_name": self.guest_name,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "metadata_json": self.metadata_json,
        }


# Compatibility alias
ChunkResult = TranscriptChunkData


class TranscriptChunker:
    """
    Segments podcast transcripts into coherent, speaker-aware chunks.
    Maintains dialogue context, timestamps, source attribution, and deterministic UUIDs.
    """

    def __init__(
        self,
        target_chunk_size: int = settings.TRANSCRIPT_CHUNK_SIZE,
        overlap_size: int = settings.TRANSCRIPT_CHUNK_OVERLAP,
        max_chunk_size: Optional[int] = None,
    ):
        self.target_chunk_size = max(50, target_chunk_size)
        self.overlap_size = max(0, min(overlap_size, int(self.target_chunk_size * 0.5)))
        self.max_chunk_size = max_chunk_size or int(self.target_chunk_size * 1.35)

    def chunk_transcript(self, transcript: ParsedTranscript) -> List[TranscriptChunkData]:
        """Chunks a ParsedTranscript into deterministic, citation-ready segments."""
        return self.chunk_turns(
            turns=transcript.turns,
            metadata=transcript.metadata,
        )

    def chunk_turns(
        self,
        turns: List[ParsedSpeakerTurn],
        metadata: TranscriptMetadata,
    ) -> List[TranscriptChunkData]:
        """
        Groups dialogue turns into bounded chunks respecting speaker turns,
        sliding overlap, and generating stable identifiers.
        """
        if not turns:
            return []

        # Step 1: Pre-process turns. If a single turn is an oversized monologue, split it.
        normalized_turns = self._normalize_turns(turns)

        chunks: List[TranscriptChunkData] = []
        seen_content_hashes: Set[str] = set()
        chunk_index = 0

        i = 0
        total_turns = len(normalized_turns)

        while i < total_turns:
            current_window: List[ParsedSpeakerTurn] = []
            current_word_count = 0

            # Accumulate turns until target size is reached
            j = i
            while j < total_turns:
                turn = normalized_turns[j]
                turn_words = len(turn.text.split())

                # If window is non-empty and adding this turn exceeds max size, stop window
                if current_window and (current_word_count + turn_words > self.max_chunk_size):
                    break

                current_window.append(turn)
                current_word_count += turn_words
                j += 1

                # If reached or exceeded target size, finalize window
                if current_word_count >= self.target_chunk_size:
                    break

            if not current_window:
                break

            # Format chunk content and metadata
            content = self._format_chunk_content(current_window)
            content_clean = content.strip()

            if content_clean:
                content_hash = hashlib.sha256(content_clean.encode("utf-8")).hexdigest()

                if content_hash not in seen_content_hashes:
                    seen_content_hashes.add(content_hash)

                    # Generate stable, deterministic UUID5
                    seed_str = f"lenny:{metadata.episode_id}:{chunk_index}:{content_hash[:16]}"
                    chunk_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_str)

                    ts_start = current_window[0].timestamp_start
                    ts_end = current_window[-1].timestamp_end
                    start_sec = current_window[0].start_seconds
                    end_sec = current_window[-1].end_seconds

                    youtube_timestamp_url = build_youtube_timestamp_url(
                        video_id=metadata.video_id,
                        youtube_url=metadata.youtube_url,
                        start_seconds=start_sec,
                    )

                    unique_speakers = list(dict.fromkeys(t.speaker for t in current_window))

                    metadata_dict: Dict[str, Any] = {
                        "youtube_url": metadata.youtube_url or "",
                        "video_id": metadata.video_id or "",
                        "youtube_timestamp_url": youtube_timestamp_url,
                        "timestamp_start_seconds": start_sec,
                        "timestamp_end_seconds": end_sec,
                        "speakers": unique_speakers,
                        "word_count": current_word_count,
                        "content_hash": content_hash,
                        "episode_content_hash": metadata.raw_content_hash,
                        "source_file": metadata.source_file,
                        "publish_date": metadata.publish_date or "",
                        "duration_seconds": metadata.duration_seconds,
                        "keywords": metadata.keywords,
                        "topic_tags": metadata.topic_tags,
                        "channel": metadata.channel,
                    }

                    chunk = TranscriptChunkData(
                        id=chunk_id,
                        episode_id=metadata.episode_id,
                        episode_title=metadata.title,
                        guest_name=metadata.guest,
                        timestamp_start=ts_start,
                        timestamp_end=ts_end,
                        chunk_index=chunk_index,
                        content=content_clean,
                        metadata_json=metadata_dict,
                    )
                    chunks.append(chunk)
                    chunk_index += 1

            # Step 2: Compute next start index based on overlap
            if j >= total_turns:
                # Reached end of transcript
                break

            # Calculate overlap turns
            overlap_words = 0
            overlap_count = 0
            for back_idx in range(j - 1, i, -1):
                turn_words = len(normalized_turns[back_idx].text.split())
                if overlap_words + turn_words <= self.overlap_size:
                    overlap_words += turn_words
                    overlap_count += 1
                else:
                    break

            next_i = j - overlap_count
            # Ensure strict forward progress
            if next_i <= i:
                next_i = i + 1

            i = next_i

        return chunks

    def _normalize_turns(self, turns: List[ParsedSpeakerTurn]) -> List[ParsedSpeakerTurn]:
        """
        Splits single turns that exceed max_chunk_size into smaller sub-turns,
        preserving speaker attribution and interpolating timestamp intervals.
        """
        normalized: List[ParsedSpeakerTurn] = []

        for turn in turns:
            words = turn.text.split()
            if len(words) <= self.max_chunk_size:
                normalized.append(turn)
                continue

            # Split monologue by paragraphs or sentences
            paragraphs = [p.strip() for p in turn.text.split("\n\n") if p.strip()]
            if len(paragraphs) > 1:
                sub_texts: List[str] = []
                cur_block: List[str] = []
                cur_wc = 0
                for p in paragraphs:
                    p_wc = len(p.split())
                    if cur_block and (cur_wc + p_wc > self.target_chunk_size):
                        sub_texts.append("\n\n".join(cur_block))
                        cur_block = [p]
                        cur_wc = p_wc
                    else:
                        cur_block.append(p)
                        cur_wc += p_wc
                if cur_block:
                    sub_texts.append("\n\n".join(cur_block))
            else:
                # Fallback: split long block by words in chunks of target_chunk_size
                sub_texts = []
                for w_start in range(0, len(words), self.target_chunk_size):
                    sub_texts.append(" ".join(words[w_start : w_start + self.target_chunk_size]))

            # Distribute time across sub-turns
            num_sub = len(sub_texts)
            total_duration = max(5, turn.end_seconds - turn.start_seconds)
            sec_per_sub = total_duration // num_sub

            cur_sec = turn.start_seconds
            for idx, text in enumerate(sub_texts):
                sub_start_sec = cur_sec
                sub_end_sec = turn.end_seconds if idx == num_sub - 1 else cur_sec + sec_per_sub
                cur_sec = sub_end_sec

                normalized.append(
                    ParsedSpeakerTurn(
                        speaker=turn.speaker,
                        timestamp_start=format_seconds_to_timestamp(sub_start_sec),
                        timestamp_end=format_seconds_to_timestamp(sub_end_sec),
                        start_seconds=sub_start_sec,
                        end_seconds=sub_end_sec,
                        text=text,
                    )
                )

        return normalized

    @staticmethod
    def _format_chunk_content(turns: List[ParsedSpeakerTurn]) -> str:
        """Formats dialogue turns into readable grounded chunk content."""
        blocks: List[str] = []
        for turn in turns:
            speaker_header = f"[{turn.speaker} ({turn.timestamp_start})]"
            blocks.append(f"{speaker_header}\n{turn.text}")
        return "\n\n".join(blocks)


def create_chunks_from_lines(
    lines: List[ParsedSpeakerTurn],
    max_chunk_size: int = settings.TRANSCRIPT_CHUNK_SIZE,
    overlap: int = settings.TRANSCRIPT_CHUNK_OVERLAP,
    episode_id: str = "episode",
    episode_title: str = "Episode",
    guest_name: str = "Guest",
    youtube_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Helper function maintaining compatibility with early Phase 1/2 function signature."""
    metadata = TranscriptMetadata(
        episode_id=episode_id,
        title=episode_title,
        guest=guest_name,
        youtube_url=youtube_url,
    )
    chunker = TranscriptChunker(target_chunk_size=max_chunk_size, overlap_size=overlap)
    chunk_objs = chunker.chunk_turns(turns=lines, metadata=metadata)
    return [c.to_dict() for c in chunk_objs]
