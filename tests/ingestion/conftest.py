"""
Pytest fixtures for transcript ingestion testing.
Provides synthetic, non-copyrighted podcast transcripts and isolated database sessions.
"""

from pathlib import Path
import sys
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure workspace and backend roots are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
for p in (str(PROJECT_ROOT), str(BACKEND_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from tests.backend.conftest import TestingSessionLocal, test_engine, Base


@pytest_asyncio.fixture
async def ingestion_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Isolated in-memory database session with fresh tables for ingestion tests."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with TestingSessionLocal() as session:
            yield session
    finally:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def synthetic_valid_markdown() -> str:
    """Synthetic valid transcript adhering to ChatPRD format."""
    return """---
guest: Alice Engineer
title: Scalable Architecture and Team Velocity
youtube_url: https://www.youtube.com/watch?v=dQw4w9WgXcQ
video_id: dQw4w9WgXcQ
publish_date: 2024-03-01
duration_seconds: 3600
channel: Lenny's Podcast
keywords:
  - architecture
  - scaling
  - velocity
description: Alice discusses scaling software architecture and team execution speed.
---

# Scalable Architecture and Team Velocity

## Transcript

Alice Engineer (00:00:00):
Welcome to the conversation. Today we are talking about building resilient distributed systems
and how modern engineering teams balance technical debt against speed to market.

Lenny (00:01:15):
That is a fascinating topic Alice. When you first evaluate a new product architecture,
what is the very first signal you look for to decide if it will survive scale?

Alice Engineer (00:02:30):
The primary signal is decoupling. If your database schemas require cross-service synchronous joins,
you will hit a ceiling very quickly. You want independent failure domains and asynchronous event boundaries.

Lenny (00:04:00):
How do you convince leadership to invest in that before everything is on fire?

Alice Engineer (00:04:45):
Frame technical debt in terms of lost business optionality and customer churn rather than purely abstract code hygiene.
"""


@pytest.fixture
def synthetic_missing_metadata_markdown() -> str:
    """Synthetic transcript with partial frontmatter (missing guest, video_id, publish_date)."""
    return """---
title: Minimalist Growth Strategies
youtube_url: https://www.youtube.com/watch?v=kXYiU_JCYtU
channel: Lenny's Podcast
---

# Minimalist Growth Strategies

Lenny (00:00:00):
What is the core idea behind minimalist growth?

Speaker (00:00:30):
Focusing exclusively on one core conversion loop before expanding across channels.
"""


@pytest.fixture
def synthetic_malformed_yaml_markdown() -> str:
    """Synthetic transcript with unclosed or broken YAML frontmatter."""
    return """---
title: [Malformed List Without Closing
guest: Bob Broken
youtube_url: https://www.youtube.com/watch?v=malformed123
---

# Recovering From Broken YAML

Lenny (00:00:00):
Did we survive the broken frontmatter?

Bob Broken (00:00:15):
Yes, safe error handling and regex extraction rescued our metadata.
"""


@pytest.fixture
def synthetic_empty_markdown() -> str:
    """Empty transcript text."""
    return "   \n\n  "


@pytest.fixture
def synthetic_monologue_markdown() -> str:
    """Synthetic transcript with a very long single speaker turn exceeding standard chunk limits."""
    sentences = [
        f"This is sentence number {i} exploring how product market fit evolves over multiple quarters."
        for i in range(1, 120)
    ]
    long_speech = " ".join(sentences)
    return f"""---
guest: Deep Thinker
title: The Long Form Philosophy of Retention
youtube_url: https://www.youtube.com/watch?v=longlong123
video_id: longlong123
duration_seconds: 5400
---

# The Long Form Philosophy of Retention

Deep Thinker (00:00:00):
{long_speech}

Lenny (00:15:00):
That was a remarkably comprehensive explanation.
"""


@pytest.fixture
def synthetic_dataset_dir(tmp_path: Path, synthetic_valid_markdown: str) -> Path:
    """Creates a mock dataset folder structure mirroring ChatPRD repository."""
    dataset_dir = tmp_path / "mock_lennys_transcripts"
    dataset_dir.mkdir()

    # Episode 1
    ep1_dir = dataset_dir / "episodes" / "alice-engineer"
    ep1_dir.mkdir(parents=True)
    (ep1_dir / "transcript.md").write_text(synthetic_valid_markdown, encoding="utf-8")

    # Episode 2
    ep2_dir = dataset_dir / "episodes" / "bob-builder"
    ep2_dir.mkdir(parents=True)
    ep2_content = """---
guest: Bob Builder
title: Can We Fix It
youtube_url: https://www.youtube.com/watch?v=bobbuilder11
video_id: bobbuilder11
publish_date: 2024-04-10
duration_seconds: 2400
keywords:
  - systems
  - tooling
---
# Can We Fix It

Bob Builder (00:00:00):
Yes we can build robust foundational tools.

Lenny (00:01:00):
What is your favourite framework?
"""
    (ep2_dir / "transcript.md").write_text(ep2_content, encoding="utf-8")

    # Index folder
    index_dir = dataset_dir / "index"
    index_dir.mkdir()
    index_pm = """# Product Management Index

- [Alice Engineer](../episodes/alice-engineer/transcript.md) - Architecture and velocity
- [Bob Builder](../episodes/bob-builder/transcript.md) - Tooling and foundation
"""
    (index_dir / "product-management.md").write_text(index_pm, encoding="utf-8")

    # README in root
    (dataset_dir / "README.md").write_text("# Lenny's Transcripts Archive", encoding="utf-8")

    return dataset_dir
