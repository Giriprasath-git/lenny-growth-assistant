"""
Unit tests for TranscriptParser in ingestion/parser.py.
Validates YAML frontmatter parsing, speaker extraction, timestamps, error resilience, and topic indexes.
"""

from pathlib import Path
import pytest
from ingestion.parser import (
    ParsedSpeakerTurn,
    ParsedTranscript,
    TranscriptParser,
    build_youtube_timestamp_url,
    compute_canonical_episode_id,
    extract_video_id_from_url,
    format_seconds_to_timestamp,
    is_valid_youtube_video_id,
    parse_timestamp_to_seconds,
    slugify,
)


def test_slugify():
    assert slugify("Brian Chesky") == "brian-chesky"
    assert slugify("Elena Verna: Growth Models 101!") == "elena-verna-growth-models-101"
    assert slugify("  Spaces & Underscores_Test  ") == "spaces-underscores-test"


def test_timestamp_parsing_and_formatting():
    # HH:MM:SS
    assert parse_timestamp_to_seconds("01:15:30") == 3600 + 900 + 30
    # MM:SS
    assert parse_timestamp_to_seconds("02:45") == 165
    # Single second
    assert parse_timestamp_to_seconds("59") == 59
    # Invalid strings
    assert parse_timestamp_to_seconds("invalid") == 0
    assert parse_timestamp_to_seconds("") == 0

    # Formatting seconds to HH:MM:SS
    assert format_seconds_to_timestamp(4530) == "01:15:30"
    assert format_seconds_to_timestamp(165) == "00:02:45"
    assert format_seconds_to_timestamp(0) == "00:00:00"


def test_youtube_video_id_extraction():
    assert extract_video_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id_from_url("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id_from_url("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id_from_url("https://youtube.com/watch?v=dQw4w9WgXcQ&t=45s") == "dQw4w9WgXcQ"
    assert extract_video_id_from_url(None) is None
    assert extract_video_id_from_url("https://example.com/not-youtube") is None


def test_youtube_timestamp_url_generation():
    assert (
        build_youtube_timestamp_url("dQw4w9WgXcQ", "https://youtube.com/watch?v=dQw4w9WgXcQ", 75)
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=75s"
    )
    assert (
        build_youtube_timestamp_url(None, "https://example.com/video", 120)
        == "https://example.com/video?t=120s"
    )
    assert build_youtube_timestamp_url(None, None, 120) == ""


def test_valid_transcript_parsing(synthetic_valid_markdown: str):
    parsed = TranscriptParser.parse_text(synthetic_valid_markdown)
    assert isinstance(parsed, ParsedTranscript)

    # Validate metadata
    meta = parsed.metadata
    assert meta.guest == "Alice Engineer"
    assert meta.title == "Scalable Architecture and Team Velocity"
    assert meta.video_id == "dQw4w9WgXcQ"
    assert meta.publish_date == "2024-03-01"
    assert meta.duration_seconds == 3600
    assert "architecture" in meta.keywords
    assert "scaling" in meta.keywords
    assert meta.channel == "Lenny's Podcast"
    assert meta.description is not None

    # Validate turns
    assert len(parsed.turns) == 5
    assert parsed.turns[0].speaker == "Alice Engineer"
    assert parsed.turns[0].timestamp_start == "00:00:00"
    assert parsed.turns[0].start_seconds == 0
    assert parsed.turns[0].end_seconds == 75  # 00:01:15

    assert parsed.turns[1].speaker == "Lenny"
    assert parsed.turns[1].timestamp_start == "00:01:15"
    assert parsed.turns[1].start_seconds == 75
    assert parsed.turns[1].end_seconds == 150  # 00:02:30

    assert parsed.turns[-1].speaker == "Alice Engineer"
    assert parsed.turns[-1].timestamp_start == "00:04:45"
    assert parsed.turns[-1].end_seconds == 3600  # Matches episode duration


def test_missing_metadata_parsing(synthetic_missing_metadata_markdown: str, tmp_path: Path):
    # Simulate a file path inside an episode folder to verify guest extraction from folder
    mock_file = tmp_path / "episodes" / "steve-growth" / "transcript.md"
    mock_file.parent.mkdir(parents=True)
    mock_file.write_text(synthetic_missing_metadata_markdown, encoding="utf-8")

    parsed = TranscriptParser.parse_file(mock_file, dataset_root=tmp_path)
    assert parsed is not None
    meta = parsed.metadata

    # Guest should be inferred from folder name rather than invented
    assert meta.guest == "Steve Growth"
    assert meta.title == "Minimalist Growth Strategies"
    # Video ID extracted from youtube_url even if missing in YAML
    assert meta.video_id == "kXYiU_JCYtU"
    assert meta.publish_date is None
    assert meta.duration_seconds is None


def test_malformed_yaml_resilience(synthetic_malformed_yaml_markdown: str):
    parsed = TranscriptParser.parse_text(synthetic_malformed_yaml_markdown)
    assert parsed is not None

    # Fallback key-value parser should rescue clean fields
    assert parsed.metadata.guest == "Bob Broken"
    assert len(parsed.turns) == 2
    assert parsed.turns[0].speaker == "Lenny"
    assert parsed.turns[1].speaker == "Bob Broken"


def test_empty_file_handling(tmp_path: Path):
    empty_file = tmp_path / "empty_transcript.md"
    empty_file.write_text("   \n\n  ", encoding="utf-8")

    result = TranscriptParser.parse_file(empty_file)
    assert result is None


def test_nonexistent_file_handling(tmp_path: Path):
    missing_file = tmp_path / "does_not_exist.md"
    result = TranscriptParser.parse_file(missing_file)
    assert result is None


def test_discover_transcript_files(synthetic_dataset_dir: Path):
    discovered = TranscriptParser.discover_transcript_files(synthetic_dataset_dir)

    # Should discover alice-engineer and bob-builder transcripts
    assert len(discovered) == 2
    filenames = [p.name for p in discovered]
    assert all(f == "transcript.md" for f in filenames)

    # Must NOT include README.md or files under index/
    for p in discovered:
        assert "index" not in p.parts
        assert p.name.lower() != "readme.md"


def test_topic_index_parsing(synthetic_dataset_dir: Path):
    index_dir = synthetic_dataset_dir / "index"
    topic_map = TranscriptParser.parse_topic_indexes(index_dir)

    assert "alice-engineer" in topic_map
    assert "product-management" in topic_map["alice-engineer"]
    assert "bob-builder" in topic_map
    assert "product-management" in topic_map["bob-builder"]


def test_canonical_episode_id_youtube_priority():
    # Valid 11-char ID
    assert is_valid_youtube_video_id("dQw4w9WgXcQ") is True
    assert is_valid_youtube_video_id("4ef0juAMqoE") is True
    # Invalid IDs
    assert is_valid_youtube_video_id("too_short") is False
    assert is_valid_youtube_video_id("way_too_long_for_youtube") is False
    assert is_valid_youtube_video_id(None) is False

    # Level 1 resolution
    ep_id = compute_canonical_episode_id(
        video_id="dQw4w9WgXcQ",
        relative_source_file="episodes/alice/transcript.md",
        title="Scalable Architecture",
    )
    assert ep_id == "yt-dQw4w9WgXcQ"


def test_two_episodes_same_title_different_video_ids():
    ep1_md = """---
guest: Guest One
title: Product Strategy AMA
youtube_url: https://www.youtube.com/watch?v=vid11111111
video_id: vid11111111
---
# Product Strategy AMA
Guest One (00:00:00): Part one text.
"""
    ep2_md = """---
guest: Guest Two
title: Product Strategy AMA
youtube_url: https://www.youtube.com/watch?v=vid22222222
video_id: vid22222222
---
# Product Strategy AMA
Guest Two (00:00:00): Part two text.
"""
    parsed1 = TranscriptParser.parse_text(ep1_md)
    parsed2 = TranscriptParser.parse_text(ep2_md)

    assert parsed1.metadata.title == parsed2.metadata.title
    assert parsed1.metadata.episode_id == "yt-vid11111111"
    assert parsed2.metadata.episode_id == "yt-vid22222222"
    assert parsed1.metadata.episode_id != parsed2.metadata.episode_id


def test_same_guest_multiple_episodes():
    ep1_md = """---
guest: Elena Verna
title: B2B Growth Strategy
youtube_url: https://www.youtube.com/watch?v=verna111111
video_id: verna111111
---
# B2B Growth Strategy
Elena Verna (00:00:00): First appearance text.
"""
    ep2_md = """---
guest: Elena Verna
title: Product-Led Sales Deep Dive
youtube_url: https://www.youtube.com/watch?v=verna222222
video_id: verna222222
---
# Product-Led Sales Deep Dive
Elena Verna (00:00:00): Second appearance text.
"""
    parsed1 = TranscriptParser.parse_text(ep1_md)
    parsed2 = TranscriptParser.parse_text(ep2_md)

    assert parsed1.metadata.guest == parsed2.metadata.guest
    assert parsed1.metadata.episode_id == "yt-verna111111"
    assert parsed2.metadata.episode_id == "yt-verna222222"
    assert parsed1.metadata.episode_id != parsed2.metadata.episode_id


def test_content_update_preserves_stable_episode_id():
    ep_before_md = """---
guest: Brian Chesky
title: Brian Chesky’s New Playbook
youtube_url: https://www.youtube.com/watch?v=4ef0juAMqoE
video_id: 4ef0juAMqoE
---
# Brian Chesky’s New Playbook
Brian Chesky (00:00:00): Initial version text.
"""
    # Simulate title revision and edited body text
    ep_after_md = """---
guest: Brian Chesky
title: Brian Chesky: How to Run a Founder-Led Company
youtube_url: https://www.youtube.com/watch?v=4ef0juAMqoE
video_id: 4ef0juAMqoE
---
# Brian Chesky: How to Run a Founder-Led Company
Brian Chesky (00:00:00): Initial version text revised with extra clarity.
Lenny (00:01:00): Follow up question.
"""
    parsed_before = TranscriptParser.parse_text(ep_before_md)
    parsed_after = TranscriptParser.parse_text(ep_after_md)

    # Titles and content hashes differ, but canonical episode_id is strictly stable
    assert parsed_before.metadata.title != parsed_after.metadata.title
    assert parsed_before.metadata.raw_content_hash != parsed_after.metadata.raw_content_hash
    assert parsed_before.metadata.episode_id == "yt-4ef0juAMqoE"
    assert parsed_after.metadata.episode_id == "yt-4ef0juAMqoE"
    assert parsed_before.metadata.episode_id == parsed_after.metadata.episode_id


def test_missing_video_id_uses_source_path(tmp_path: Path):
    ep_md = """---
guest: Steve Growth
title: Offline Minimalist Strategy
---
# Offline Minimalist Strategy
Steve Growth (00:00:00): Local recording text.
"""
    mock_file = tmp_path / "episodes" / "steve-growth" / "transcript.md"
    mock_file.parent.mkdir(parents=True)
    mock_file.write_text(ep_md, encoding="utf-8")

    parsed = TranscriptParser.parse_file(mock_file, dataset_root=tmp_path)
    assert parsed is not None
    assert parsed.metadata.video_id is None
    # Level 2 resolution: normalized source path slug
    assert parsed.metadata.episode_id == "path-episodes-steve-growth"


def test_raw_text_without_video_id_or_path_fallback():
    # Has title, but no video_id or path
    ep_text = """---
guest: Mystery Guest
title: Hidden Gems of Retention
---
Mystery Guest (00:00:00): Text here.
"""
    parsed_title = TranscriptParser.parse_text(ep_text)
    assert parsed_title.metadata.episode_id == "title-hidden-gems-of-retention"

    # No title, no video_id, no path
    ep_no_title = "Mystery Guest (00:00:00): Text here."
    parsed_hash = TranscriptParser.parse_text(ep_no_title)
    assert parsed_hash.metadata.episode_id.startswith("hash-")
