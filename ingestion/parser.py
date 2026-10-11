"""
Podcast transcript parsing utilities for The Lenny Growth Assistant.
Tailored for the ChatPRD/lennys-podcast-transcripts Markdown repository structure.
Extracts YAML frontmatter, speaker turns, timestamps, and metadata with safe error handling.
"""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import yaml
from backend.app.core.logging import logger

# Regex to safely isolate YAML frontmatter bounded by triple-dashes
FRONTMATTER_PATTERN = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", re.DOTALL)

# Regex matching dialogue speaker turns, e.g.:
# "Brian Chesky (00:00:00):" or "Lenny Rachitsky (01:05):" or "### Guest [00:02:15]:"
SPEAKER_TURN_PATTERN = re.compile(
    r"^(?:#{1,4}\s*|\*{1,2})?([A-Za-z0-9\s\.\'\-–—]+?)(?:\*{1,2})?\s*[\(\[](\d{1,2}:\d{2}(?::\d{2})?)[\)\]]\s*:\s*(.*)$"
)

# Regex to extract 11-character YouTube video ID from various URL formats
YOUTUBE_VIDEO_ID_PATTERN = re.compile(
    r"(?:v=|youtu\.be\/|embed\/|\/v\/|watch\?v=)([a-zA-Z0-9_-]{11})"
)


def slugify(text: str) -> str:
    """Converts a string to a clean URL/storage-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def parse_timestamp_to_seconds(ts_str: str) -> int:
    """
    Converts a timestamp string (HH:MM:SS or MM:SS) into integer total seconds.
    Returns 0 if parsing fails.
    """
    ts_str = ts_str.strip()
    parts = ts_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1 and parts[0].isdigit():
            return int(parts[0])
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse timestamp '{ts_str}', defaulting to 0s")
    return 0


def format_seconds_to_timestamp(seconds: int) -> str:
    """Formats integer seconds into standard HH:MM:SS string."""
    seconds = max(0, seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def extract_video_id_from_url(url: Optional[str]) -> Optional[str]:
    """Extracts YouTube video ID from standard or shortened YouTube URLs."""
    if not url:
        return None
    match = YOUTUBE_VIDEO_ID_PATTERN.search(url)
    return match.group(1) if match else None


def build_youtube_timestamp_url(video_id: Optional[str], youtube_url: Optional[str], start_seconds: int) -> str:
    """Builds a direct link to the specific YouTube video timestamp."""
    start_sec = max(0, start_seconds)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s"
    if youtube_url:
        delimiter = "&" if "?" in youtube_url else "?"
        return f"{youtube_url}{delimiter}t={start_sec}s"
    return ""


def is_valid_youtube_video_id(video_id: Optional[str]) -> bool:
    """
    Validates whether a string is a standard 11-character YouTube video ID.
    YouTube IDs consist of exactly 11 base64-URL characters [a-zA-Z0-9_-].
    """
    if not video_id or not isinstance(video_id, str):
        return False
    return bool(re.match(r"^[a-zA-Z0-9_-]{11}$", video_id.strip()))


def compute_canonical_episode_id(
    video_id: Optional[str] = None,
    relative_source_file: Optional[str] = None,
    source_path: Optional[Path] = None,
    title: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> str:
    """
    Computes a canonical, collision-free episode identifier adhering to the 3-level hierarchy:
    1. Validated YouTube Video ID: 'yt-{video_id}' (case-sensitive, permanent, immune to title/content updates).
    2. Repository-relative source path: 'path-{normalized_slug}' (stable when video ID is missing).
    3. Deterministic fallback: 'title-{normalized_slug}' if title is meaningful, else 'hash-{content_hash[:16]}'.
    """
    # Level 1: Validated YouTube Video ID
    if is_valid_youtube_video_id(video_id):
        return f"yt-{video_id.strip()}"

    # Level 2: Repository-relative source path
    candidate_path = relative_source_file
    if not candidate_path and source_path:
        candidate_path = str(source_path)

    if candidate_path:
        # Normalize Windows backslashes and remove transcript.md / .md extensions
        normalized = candidate_path.replace("\\", "/").strip("/")
        normalized = re.sub(r"/(?:transcript)?\.md$", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\.md$", "", normalized, flags=re.IGNORECASE)
        # Replace directory separators with hyphen so path slugs preserve folder tokens
        normalized = normalized.replace("/", "-")
        slug_path = slugify(normalized)
        if slug_path:
            return f"path-{slug_path}"

    # Level 3: Deterministic fallback
    if title and title.strip().lower() not in {"untitled episode", "untitled", "transcript"}:
        slug_title = slugify(title)
        if slug_title:
            return f"title-{slug_title}"

    # Absolute fallback: content hash or unknown prefix
    hash_prefix = (content_hash[:16] if content_hash else "unknown")
    return f"hash-{hash_prefix}"


@dataclass

class ParsedSpeakerTurn:
    """Represents a single continuous speaker dialogue turn."""
    speaker: str
    timestamp_start: str
    timestamp_end: str
    start_seconds: int
    end_seconds: int
    text: str


# Backward compatibility alias for Phase 1/2 tests
ParsedTranscriptLine = ParsedSpeakerTurn


@dataclass
class TranscriptMetadata:
    """Structured metadata extracted from YAML frontmatter and file context."""
    episode_id: str
    title: str
    guest: str
    youtube_url: Optional[str] = None
    video_id: Optional[str] = None
    publish_date: Optional[str] = None
    duration_seconds: Optional[int] = None
    channel: str = "Lenny's Podcast"
    keywords: List[str] = field(default_factory=list)
    description: Optional[str] = None
    source_file: str = ""
    raw_content_hash: str = ""
    topic_tags: List[str] = field(default_factory=list)


@dataclass
class ParsedTranscript:
    """Complete parsed transcript including frontmatter metadata and structured dialogue turns."""
    metadata: TranscriptMetadata
    turns: List[ParsedSpeakerTurn]
    raw_text: str

    @property
    def total_words(self) -> int:
        return sum(len(turn.text.split()) for turn in self.turns)


class TranscriptParser:
    """
    Parses Markdown transcripts from ChatPRD/lennys-podcast-transcripts repository.
    Extracts YAML frontmatter, turns, timestamps, and supplemental topic tags.
    """

    @classmethod
    def discover_transcript_files(cls, root_dir: Path) -> List[Path]:
        """
        Recursively discovers all transcript Markdown files under root_dir.
        Detects both 'transcript.md' within episode subfolders and standalone episode markdown files.
        Avoids index/ files and READMEs.
        """
        if not root_dir.exists():
            return []

        discovered: List[Path] = []
        if root_dir.is_file():
            return [root_dir]

        # Scan for transcript.md or .md files in episode directories
        for path in sorted(root_dir.rglob("*.md")):
            # Ignore root READMEs, index catalogs, and script documents
            parts = [p.lower() for p in path.parts]
            if "index" in parts or "scripts" in parts or path.name.lower() in {"readme.md", "claude.md"}:
                continue
            discovered.append(path)

        return discovered

    @classmethod
    def parse_file(
        cls,
        file_path: Path,
        dataset_root: Optional[Path] = None,
        topic_index: Optional[Dict[str, List[str]]] = None,
    ) -> Optional[ParsedTranscript]:
        """
        Reads and parses an episode Markdown transcript file safely.
        Returns None if file is empty or missing.
        """
        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"Transcript file not found: {file_path}")
            return None

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None

        if not content.strip():
            logger.warning(f"Transcript file is empty: {file_path}")
            return None

        # Determine relative source path
        if dataset_root:
            try:
                rel_path = str(file_path.relative_to(dataset_root)).replace("\\", "/")
            except ValueError:
                rel_path = str(file_path).replace("\\", "/")
        else:
            rel_path = str(file_path).replace("\\", "/")

        return cls.parse_text(
            content=content,
            source_path=file_path,
            relative_source_file=rel_path,
            topic_index=topic_index,
        )

    @classmethod
    def parse_text(
        cls,
        content: str,
        source_path: Optional[Path] = None,
        relative_source_file: str = "",
        topic_index: Optional[Dict[str, List[str]]] = None,
    ) -> ParsedTranscript:
        """
        Parses transcript text containing YAML frontmatter and dialogue turns.
        """
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Step 1: Extract YAML frontmatter and Markdown body
        frontmatter_data: Dict[str, Any] = {}
        body_text = content

        fm_match = FRONTMATTER_PATTERN.match(content)
        if fm_match:
            fm_raw = fm_match.group(1)
            body_text = fm_match.group(2)
            try:
                loaded = yaml.safe_load(fm_raw)
                if isinstance(loaded, dict):
                    frontmatter_data = loaded
            except yaml.YAMLError as exc:
                logger.warning(f"Malformed YAML frontmatter in {relative_source_file or 'text'}: {exc}")
                # Safe regex fallback for basic key-value extraction
                frontmatter_data = cls._fallback_parse_yaml(fm_raw)

        # Step 2: Determine episode ID and metadata
        dir_name = source_path.parent.name if source_path and source_path.parent.name not in {"episodes", "raw_transcripts", "data", "."} else ""
        file_stem = source_path.stem if source_path and source_path.stem != "transcript" else ""
        
        # Determine guest name
        guest = frontmatter_data.get("guest") or ""
        if not guest and dir_name:
            guest = dir_name.replace("-", " ").title()
        elif not guest and file_stem:
            guest = file_stem.replace("-", " ").title()

        # Determine episode title
        title = frontmatter_data.get("title") or ""
        if not title:
            # Fallback: inspect top # heading in body
            title_match = re.search(r"^#\s+(.+)$", body_text, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()
            elif guest:
                title = f"{guest} - Lenny's Podcast"
            else:
                title = "Untitled Episode"

        # YouTube attributes
        youtube_url = frontmatter_data.get("youtube_url")
        video_id = frontmatter_data.get("video_id")
        if not video_id and youtube_url:
            video_id = extract_video_id_from_url(youtube_url)

        # Determine canonical episode_id
        episode_id = compute_canonical_episode_id(
            video_id=video_id,
            relative_source_file=relative_source_file,
            source_path=source_path,
            title=title,
            content_hash=content_hash,
        )

        # Duration
        duration_raw = frontmatter_data.get("duration_seconds")
        duration_seconds: Optional[int] = None
        if duration_raw is not None:
            try:
                duration_seconds = int(duration_raw)
            except (ValueError, TypeError):
                duration_seconds = parse_timestamp_to_seconds(str(duration_raw))

        # Publish date
        publish_date = str(frontmatter_data.get("publish_date")) if frontmatter_data.get("publish_date") else None

        # Keywords
        raw_keywords = frontmatter_data.get("keywords")
        keywords: List[str] = []
        if isinstance(raw_keywords, list):
            keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
        elif isinstance(raw_keywords, str):
            keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

        # Channel
        channel = str(frontmatter_data.get("channel") or "Lenny's Podcast")

        # Description
        description = frontmatter_data.get("description")
        if description is not None:
            description = str(description).strip()

        # Topic tags from supplemental index
        topic_tags: List[str] = []
        if topic_index:
            tags = topic_index.get(episode_id, [])
            if not tags and video_id:
                tags = topic_index.get(video_id, [])
            if not tags and relative_source_file:
                clean_path = slugify(re.sub(r"/(?:transcript)?\.md$", "", relative_source_file, flags=re.IGNORECASE))
                tags = topic_index.get(clean_path, [])
            if not tags and dir_name:
                tags = topic_index.get(slugify(dir_name), [])
            if not tags and guest:
                tags = topic_index.get(slugify(guest), [])
            topic_tags = sorted(list(set(tags)))

        metadata = TranscriptMetadata(
            episode_id=episode_id,
            title=title,
            guest=guest,
            youtube_url=youtube_url,
            video_id=video_id,
            publish_date=publish_date,
            duration_seconds=duration_seconds,
            channel=channel,
            keywords=keywords,
            description=description,
            source_file=relative_source_file or (str(source_path) if source_path else ""),
            raw_content_hash=content_hash,
            topic_tags=topic_tags,
        )

        # Step 3: Parse dialogue speaker turns
        turns = cls._parse_speaker_turns(body_text, episode_duration=duration_seconds)

        return ParsedTranscript(
            metadata=metadata,
            turns=turns,
            raw_text=body_text,
        )

    @classmethod
    def _fallback_parse_yaml(cls, raw_yaml: str) -> Dict[str, Any]:
        """Line-by-line fallback extractor for simple key-value pairs in malformed YAML."""
        data: Dict[str, Any] = {}
        for line in raw_yaml.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            kv_match = re.match(r"^([a-zA-Z_0-9-]+)\s*:\s*(.*)$", line)
            if kv_match:
                key = kv_match.group(1).strip()
                val = kv_match.group(2).strip().strip("'\"")
                data[key] = val
        return data

    @classmethod
    def _parse_speaker_turns(cls, body_text: str, episode_duration: Optional[int] = None) -> List[ParsedSpeakerTurn]:
        """
        Parses Markdown transcript body into structured speaker turns.
        Matches speaker turn headers (e.g. 'Name (HH:MM:SS):') and groups multi-line speeches.
        """
        lines = body_text.splitlines()
        raw_turns: List[Dict[str, Any]] = []
        current_turn: Optional[Dict[str, Any]] = None

        for line in lines:
            stripped = line.strip()
            match = SPEAKER_TURN_PATTERN.match(stripped)

            if match:
                # Flush previous turn
                if current_turn:
                    current_turn["text"] = "\n".join(current_turn["text_lines"]).strip()
                    if current_turn["text"]:
                        raw_turns.append(current_turn)

                speaker = match.group(1).strip()
                timestamp_str = match.group(2).strip()
                first_text = match.group(3).strip()

                start_secs = parse_timestamp_to_seconds(timestamp_str)
                formatted_start = format_seconds_to_timestamp(start_secs)

                current_turn = {
                    "speaker": speaker,
                    "timestamp_start": formatted_start,
                    "start_seconds": start_secs,
                    "text_lines": [first_text] if first_text else [],
                }
            elif current_turn:
                # Filter out pure markdown headings like "## Transcript" or "# Title"
                if stripped.startswith("#"):
                    continue
                current_turn["text_lines"].append(line)

        # Flush final turn
        if current_turn:
            current_turn["text"] = "\n".join(current_turn["text_lines"]).strip()
            if current_turn["text"]:
                raw_turns.append(current_turn)

        # If no speaker turns were detected with pattern, fallback to paragraph chunking
        if not raw_turns:
            return cls._fallback_paragraph_turns(body_text, episode_duration)

        # Calculate timestamp_end and end_seconds for each turn
        parsed_turns: List[ParsedSpeakerTurn] = []
        for i, t in enumerate(raw_turns):
            start_sec = t["start_seconds"]
            if i + 1 < len(raw_turns):
                next_start = raw_turns[i + 1]["start_seconds"]
                end_sec = max(start_sec, next_start)
            elif episode_duration and episode_duration >= start_sec:
                end_sec = episode_duration
            else:
                # Estimate 150 words per minute for remaining monologue
                word_count = len(t["text"].split())
                end_sec = start_sec + max(5, int(word_count * 0.4))

            end_ts = format_seconds_to_timestamp(end_sec)

            parsed_turns.append(
                ParsedSpeakerTurn(
                    speaker=t["speaker"],
                    timestamp_start=t["timestamp_start"],
                    timestamp_end=end_ts,
                    start_seconds=start_sec,
                    end_seconds=end_sec,
                    text=t["text"],
                )
            )

        return parsed_turns

    @classmethod
    def _fallback_paragraph_turns(cls, body_text: str, episode_duration: Optional[int] = None) -> List[ParsedSpeakerTurn]:
        """Fallback when transcripts lack speaker markers (plain narrative/text)."""
        paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip() and not p.strip().startswith("#")]
        if not paragraphs:
            return []

        turns: List[ParsedSpeakerTurn] = []
        current_sec = 0
        step_sec = (episode_duration // len(paragraphs)) if episode_duration and len(paragraphs) > 0 else 60
        step_sec = max(10, step_sec)

        for p in paragraphs:
            start_ts = format_seconds_to_timestamp(current_sec)
            end_sec = current_sec + step_sec
            end_ts = format_seconds_to_timestamp(end_sec)
            turns.append(
                ParsedSpeakerTurn(
                    speaker="Speaker",
                    timestamp_start=start_ts,
                    timestamp_end=end_ts,
                    start_seconds=current_sec,
                    end_seconds=end_sec,
                    text=p,
                )
            )
            current_sec = end_sec

        return turns

    @classmethod
    def parse_topic_indexes(cls, index_dir: Path) -> Dict[str, List[str]]:
        """
        Parses topic markdown files in index/ directory (e.g. growth-strategy.md, product-management.md).
        Returns a mapping of episode slug/guest to a list of topic tags.
        """
        if not index_dir.exists() or not index_dir.is_dir():
            return {}

        topic_mapping: Dict[str, List[str]] = {}
        for md_file in sorted(index_dir.glob("*.md")):
            if md_file.name.lower() == "readme.md":
                continue
            topic_tag = md_file.stem.lower()

            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Look for markdown links e.g. [Guest - Title](../episodes/brian-chesky/transcript.md)
            # or (/episodes/brian-chesky)
            links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
            for label, link in links:
                ep_match = re.search(r"episodes\/([a-zA-Z0-9_-]+)", link)
                if ep_match:
                    slug = ep_match.group(1).lower()
                    topic_mapping.setdefault(slug, []).append(topic_tag)
                else:
                    # Map based on label guest name
                    slug = slugify(label)
                    topic_mapping.setdefault(slug, []).append(topic_tag)

        # De-duplicate topic tags
        return {k: sorted(list(set(v))) for k, v in topic_mapping.items()}
