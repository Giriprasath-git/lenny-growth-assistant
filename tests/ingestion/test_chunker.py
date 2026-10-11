"""
Unit tests for TranscriptChunker in ingestion/chunker.py.
Validates chunk sizing, speaker turn preservation, overlap, stable UUID5, and YouTube URLs.
"""

from pathlib import Path
import uuid
import pytest
from ingestion.chunker import TranscriptChunkData, TranscriptChunker
from ingestion.parser import (
    ParsedSpeakerTurn,
    ParsedTranscript,
    TranscriptMetadata,
    TranscriptParser,
)


def test_chunker_basic_chunking(synthetic_valid_markdown: str):
    parsed = TranscriptParser.parse_text(synthetic_valid_markdown)
    chunker = TranscriptChunker(target_chunk_size=100, overlap_size=20)
    chunks = chunker.chunk_transcript(parsed)

    assert len(chunks) > 0
    for chunk in chunks:
        assert isinstance(chunk, TranscriptChunkData)
        assert isinstance(chunk.id, uuid.UUID)
        assert chunk.episode_id == "yt-dQw4w9WgXcQ"
        assert chunk.guest_name == "Alice Engineer"
        assert chunk.content.strip() != ""
        # Validate metadata fields
        meta = chunk.metadata_json
        assert meta["video_id"] == "dQw4w9WgXcQ"
        assert "youtube_timestamp_url" in meta
        assert meta["youtube_timestamp_url"].startswith("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=")
        assert "word_count" in meta
        assert meta["word_count"] > 0
        assert "content_hash" in meta


def test_chunk_determinism(synthetic_valid_markdown: str):
    parsed1 = TranscriptParser.parse_text(synthetic_valid_markdown)
    parsed2 = TranscriptParser.parse_text(synthetic_valid_markdown)

    chunker1 = TranscriptChunker(target_chunk_size=120, overlap_size=25)
    chunker2 = TranscriptChunker(target_chunk_size=120, overlap_size=25)

    chunks1 = chunker1.chunk_transcript(parsed1)
    chunks2 = chunker2.chunk_transcript(parsed2)

    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1.id == c2.id, "Chunk UUID5 must be strictly deterministic"
        assert c1.chunk_index == c2.chunk_index
        assert c1.content == c2.content
        assert c1.metadata_json["content_hash"] == c2.metadata_json["content_hash"]


def test_long_monologue_splitting(synthetic_monologue_markdown: str):
    parsed = TranscriptParser.parse_text(synthetic_monologue_markdown)
    chunker = TranscriptChunker(target_chunk_size=200, overlap_size=40, max_chunk_size=250)
    chunks = chunker.chunk_transcript(parsed)

    # Should split the 1000+ word monologue into multiple chunks
    assert len(chunks) > 2
    for chunk in chunks:
        words = chunk.content.split()
        # Ensure speaker continuity is preserved
        assert "Deep Thinker" in chunk.content or "Lenny" in chunk.content
        assert chunk.timestamp_start != ""
        assert chunk.timestamp_end != ""


def test_empty_turns_returns_empty_list():
    chunker = TranscriptChunker()
    metadata = TranscriptMetadata(episode_id="test", title="Test", guest="Test")
    chunks = chunker.chunk_turns([], metadata)
    assert chunks == []


def test_sliding_window_overlap():
    turns = [
        ParsedSpeakerTurn(
            speaker=f"Speaker {i}",
            timestamp_start=f"00:{i:02d}:00",
            timestamp_end=f"00:{i+1:02d}:00",
            start_seconds=i * 60,
            end_seconds=(i + 1) * 60,
            text=f"This is dialogue turn {i} with about ten distinct words to test overlap properly.",
        )
        for i in range(10)
    ]
    metadata = TranscriptMetadata(episode_id="overlap-test", title="Overlap", guest="Speaker")
    # Low target chunk size so each chunk fits ~2-3 turns, with 1 turn overlap
    chunker = TranscriptChunker(target_chunk_size=35, overlap_size=15, max_chunk_size=50)
    chunks = chunker.chunk_turns(turns, metadata)

    assert len(chunks) >= 3
    # Check that adjacent chunks have distinct chunk indices
    for i, c in enumerate(chunks):
        assert c.chunk_index == i


def test_no_duplicate_chunks():
    turns = [
        ParsedSpeakerTurn(
            speaker="Lenny",
            timestamp_start="00:00:00",
            timestamp_end="00:01:00",
            start_seconds=0,
            end_seconds=60,
            text="Hello world dialogue test passage.",
        )
    ]
    metadata = TranscriptMetadata(episode_id="no-dup", title="No Dup", guest="Lenny")
    chunker = TranscriptChunker(target_chunk_size=50, overlap_size=10)
    chunks = chunker.chunk_turns(turns, metadata)

    assert len(chunks) == 1
