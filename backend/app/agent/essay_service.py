"""
Dedicated Ship 30 for 30 Essay Generation Service.
Implements structured digital writing synthesis grounded in Lenny's Podcast archives
with support for multiple tones, target audiences, lengths, and model providers.
"""

from datetime import datetime, timezone
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.agent.providers.base import BaseLLMProvider, ChatMessageInput, CompletionResult
from backend.app.agent.providers.cloud import CloudAnthropicProvider
from backend.app.agent.providers.gemini import GeminiProvider
from backend.app.agent.providers.ollama import OllamaProvider
from backend.app.agent.providers.pi_agent import PiAgentProvider
from backend.app.core.config import settings
from backend.app.core.exceptions import ProviderUnavailableError, SessionNotFoundError
from backend.app.core.logging import logger
from backend.app.db.models.message import ChatMessage, MessageCitation
from backend.app.db.models.session import ChatSession
from backend.app.rag.retriever import GroundedEvidence, TranscriptRetriever
from backend.app.schemas.essay import EssayGenerateRequest, EssayListResponse, EssayResponse
from backend.app.schemas.session import CitationResponse


# Target word count mappings
LENGTH_TARGETS: Dict[str, int] = {
    "short": 300,
    "medium": 600,
    "deep_dive": 1250,
}

# Max output tokens tailored to 8 GB RAM local hardware limits
LOCAL_TOKEN_BUDGETS: Dict[str, int] = {
    "short": 600,
    "medium": 950,
    "deep_dive": 1500,
}

# Cloud model token budgets (unconstrained by local 8 GB RAM limits; 3,200 tokens guarantees ~1,250 words)
CLOUD_TOKEN_BUDGETS: Dict[str, int] = {
    "short": 800,
    "medium": 1500,
    "deep_dive": 3200,
}

# Preserved for backward compatibility
LENGTH_TOKEN_BUDGETS: Dict[str, int] = LOCAL_TOKEN_BUDGETS


def get_token_budget(provider_name: str, desired_length: str) -> int:
    """Returns provider-specific token budget, keeping local Ollama bounded to 8 GB RAM limits."""
    length_key = desired_length if desired_length in LENGTH_TARGETS else "deep_dive"
    if provider_name.lower() in ("cloud", "gemini", "anthropic"):
        return CLOUD_TOKEN_BUDGETS.get(length_key, 3200)
    return LOCAL_TOKEN_BUDGETS.get(length_key, 1500)


class EssayGenerationService:
    """Orchestrates structured Ship 30 for 30 essay generation, grounding, and persistence."""

    def __init__(self) -> None:
        self.retriever = TranscriptRetriever()

    def _resolve_provider(
        self,
        requested_provider: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> Tuple[BaseLLMProvider, str, str]:
        """Resolves the LLM provider adapter according to requested provider or local Ollama default."""
        provider_name = (requested_provider or settings.DEFAULT_LLM_PROVIDER).lower()

        if provider_name in ("cloud", "gemini"):
            gemini_provider = GeminiProvider()
            if not gemini_provider.is_configured:
                raise ProviderUnavailableError(
                    provider="gemini",
                    message=(
                        "Cloud Gemini is not configured on this server. "
                        "A GEMINI_API_KEY environment variable is required for cloud generation. "
                        "Please select Local LLM (Ollama) to generate essays offline."
                    ),
                    status_code=503,
                )
            return gemini_provider, "cloud", settings.GEMINI_MODEL

        elif provider_name == "pi_agent":
            pi_provider = PiAgentProvider(model=model_override or settings.PI_AGENT_MODEL)
            return pi_provider, "pi_agent", model_override or settings.PI_AGENT_MODEL

        elif provider_name == "anthropic":
            anthropic_provider = CloudAnthropicProvider(model=model_override or settings.ANTHROPIC_MODEL)
            if not anthropic_provider.is_configured:
                raise ProviderUnavailableError(
                    provider="anthropic",
                    message="Anthropic Cloud provider is not configured. Please use local Ollama.",
                    status_code=503,
                )
            return anthropic_provider, "anthropic", model_override or settings.ANTHROPIC_MODEL

        else:
            # Local Ollama is development default
            target_model = model_override or settings.OLLAMA_MODEL
            ollama_provider = OllamaProvider(model=target_model)
            return ollama_provider, "ollama", target_model

    def _build_essay_prompt(
        self,
        topic: str,
        target_audience: str,
        tone: str,
        desired_length: str,
        target_words: int,
        specific_instructions: Optional[str] = None,
        grounding_context: str = "",
        has_evidence: bool = False,
    ) -> Tuple[str, str]:
        """
        Constructs system prompt and grounded user prompt adhering to Ship 30 for 30 principles:
        compelling hook, 1-3-1 rhythm, modular sections, and rate of revelation.
        Calibrates sections (5 core pillars for deep-dive) to reliably hit word count targets.
        """
        if desired_length == "deep_dive":
            structure_format = f"""OUTPUT FORMAT REQUIREMENTS (DEEP-DIVE ESSAY ~1,100–1,350 WORDS, TARGET: ~1,250 WORDS):
# [Main Headline Hook]

**Hook:** [1-2 paragraphs (~100-140 words) establishing the high-stakes problem, counterintuitive truth, and specific promised transformation]

## 1. [First Core Pillar Title]
[Thoroughly articulated section (~180-220 words) with lead insight sentence, 3 bulleted operational mechanics/case details, and punchy concluding line]

## 2. [Second Core Pillar Title]
[Thoroughly articulated section (~180-220 words) with lead insight sentence, 3 bulleted operational mechanics/case details, and punchy concluding line]

## 3. [Third Core Pillar Title]
[Thoroughly articulated section (~180-220 words) with lead insight sentence, 3 bulleted operational mechanics/case details, and punchy concluding line]

## 4. [Fourth Core Pillar Title]
[Thoroughly articulated section (~180-220 words) with lead insight sentence, 3 bulleted operational mechanics/case details, and punchy concluding line]

## 5. [Fifth Core Pillar Title]
[Thoroughly articulated section (~180-220 words) with lead insight sentence, 3 bulleted operational mechanics/case details, and punchy concluding line]

## The Tactical Takeaway
[Definitive synthesis followed by a concrete 5-step implementation checklist (~150-200 words)]

---
### Alternative Headlines:
1. [Formula 1 Headline]
2. [Formula 2 Headline]
3. [Formula 3 Headline]"""
        elif desired_length == "medium":
            structure_format = f"""OUTPUT FORMAT REQUIREMENTS (MEDIUM ESSAY ~600 WORDS):
# [Main Headline Hook]

**Hook:** [1 paragraph (~60-80 words) opening hook]

## 1. [First Section Title]
[Content following 1-3-1 rhythm (~140-160 words)]

## 2. [Second Section Title]
[Content following 1-3-1 rhythm (~140-160 words)]

## 3. [Third Section Title]
[Content following 1-3-1 rhythm (~140-160 words)]

## The Tactical Takeaway
[Summary and 3-step action plan (~80-100 words)]

---
### Alternative Headlines:
1. [Formula 1 Headline]
2. [Formula 2 Headline]
3. [Formula 3 Headline]"""
        else:
            structure_format = f"""OUTPUT FORMAT REQUIREMENTS (ATOMIC ESSAY ~300 WORDS):
# [Main Headline Hook]

**Hook:** [1-2 sentence hook opening (~40-50 words)]

## 1. [First Section Title]
[Tight 1-3-1 content (~70-80 words)]

## 2. [Second Section Title]
[Tight 1-3-1 content (~70-80 words)]

## 3. [Third Section Title]
[Tight 1-3-1 content (~70-80 words)]

## The Tactical Takeaway
[Crisp takeaway sentence (~40-50 words)]

---
### Alternative Headlines:
1. [Formula 1 Headline]
2. [Formula 2 Headline]
3. [Formula 3 Headline]"""

        system_prompt = f"""You are an elite digital writer and growth practitioner trained in structured nonfiction essay writing (inspired by the Ship 30 for 30 methodology).

YOUR WRITING PRINCIPLES:
1. THE ATOMIC HOOK: Start with an irresistible, benefit-driven headline hook that promises a specific transformation.
2. AUDIENCE CALIBRATION: Write specifically for: {target_audience}.
3. TONE: {tone.capitalize()} - crisp, high-signal, zero corporate jargon, and actionable.
4. TARGET LENGTH: Approximately {target_words} words (Deep-Dive acceptance range: 1,100–1,350 words). Expand depth through concrete operational mechanics, counterintuitive nuances, and real frameworks, not repetitive filler.
5. 1-3-1 VISUAL CADENCE:
   - One bold lead sentence.
   - Three tight, punchy supporting insights or bullet points.
   - One memorable conclusion line.
   Never write dense 10-line text walls.
6. THE RATE OF REVELATION: Maximize insight density per sentence. Eliminate throat-clearing openings ("In this essay...", "It is important to note...").
7. CLOSING TAKEAWAY: End with a definitive, tactical implementation checklist or takeaway.

{structure_format}
"""

        grounding_instructions = ""
        if has_evidence:
            grounding_instructions = f"""
PODCAST EVIDENCE FROM LENNY'S ARCHIVES:
The following transcript passages were retrieved from Lenny Rachitsky's podcast.
Synthesize these genuine perspectives into the essay. When incorporating an idea or quote from this evidence, reference the guest or use citation markers: [1], [2].
Do NOT fabricate quotes, invent fake episode timestamps, or invent unsupported statistics.

<podcast_evidence>
{grounding_context}
</podcast_evidence>
"""
        elif grounding_context:
            grounding_instructions = "\nNote: No direct podcast transcripts matched this topic. Write from general product management and growth principles without fabricated citations.\n"

        custom_notes = f"\nSpecific Instructions: {specific_instructions}\n" if specific_instructions else ""

        user_prompt = f"""Please write a structured Ship 30 for 30 essay on the following topic:

Topic: {topic}
Target Audience: {target_audience}
Tone: {tone}
Desired Depth: {desired_length} (Target: ~{target_words} words, practical acceptance range: 1,100–1,350 words for deep-dive)
{custom_notes}
{grounding_instructions}

Deliver the complete, fully articulated essay now adhering strictly to the headline formulas, 1-3-1 cadence, and output structure."""

        return system_prompt, user_prompt

    def _parse_essay_output(
        self,
        raw_text: str,
        topic: str,
        target_words: int,
        provider_name: str = "ollama",
        finish_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extracts title, hook, alternative titles, takeaway, and word count statistics from generated text."""
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

        # Extract title
        title = ""
        for line in lines:
            if line.startswith("# ") and not line.startswith("### "):
                title = line.lstrip("# ").strip()
                break
            elif line.lower().startswith("title:"):
                title = line.split(":", 1)[1].strip()
                break

        if not title:
            # Fallback to topic-based headline
            title = f"The Growth Playbook: How To Master {topic}"

        # Extract Hook
        headline_hook = ""
        hook_match = re.search(r"\*\*Hook:\*\*\s*(.*?)(?=\n\n|\n##|$)", raw_text, re.DOTALL | re.IGNORECASE)
        if hook_match:
            headline_hook = hook_match.group(1).strip()
        elif len(lines) > 1:
            headline_hook = lines[1]

        # Extract Alternative Headlines
        alternative_titles: List[str] = []
        alt_section = re.search(r"###\s*Alternative Headlines?:?\s*(.*?)$", raw_text, re.DOTALL | re.IGNORECASE)
        if alt_section:
            alt_lines = alt_section.group(1).strip().split("\n")
            for al in alt_lines:
                clean_alt = re.sub(r"^\d+[\.\)]\s*|-\s*", "", al.strip()).strip()
                if clean_alt and len(clean_alt) > 5:
                    alternative_titles.append(clean_alt)

        # Extract Takeaway
        takeaway = ""
        takeaway_match = re.search(r"##\s*(?:The Tactical )?Takeaway:?\s*(.*?)(?=\n---|###|$)", raw_text, re.DOTALL | re.IGNORECASE)
        if takeaway_match:
            takeaway = takeaway_match.group(1).strip()

        # Word count analysis
        words = raw_text.split()
        actual_word_count = len(words)

        # Evaluate word count compliance
        # Acceptance range: for target >= 1000, 85% threshold (1,062 words) accepts ~1,100-1,350 words cleanly
        min_threshold = int(target_words * 0.85) if target_words >= 1000 else int(target_words * 0.75)
        if actual_word_count >= min_threshold:
            word_count_status = "target_achieved"
            word_count_note = None
        else:
            word_count_status = "bounded_by_model_output"
            is_cloud = provider_name.lower() in ("cloud", "gemini", "anthropic")
            if is_cloud:
                if finish_reason == "MAX_TOKENS":
                    word_count_note = (
                        f"Generated {actual_word_count} words against requested ~{target_words} words. "
                        "Cloud model reached maximum output token budget."
                    )
                else:
                    word_count_note = (
                        f"Generated {actual_word_count} words against requested ~{target_words} words. "
                        f"Cloud model completed generation within available output limits ({finish_reason or 'complete'})."
                    )
            else:
                word_count_note = (
                    f"Generated {actual_word_count} words against requested ~{target_words} words. "
                    "Local model inference token budget bounded output to preserve 8 GB RAM stability."
                )

        return {
            "title": title,
            "headline_hook": headline_hook,
            "alternative_titles": alternative_titles[:4],
            "takeaway": takeaway,
            "actual_word_count": actual_word_count,
            "word_count_status": word_count_status,
            "word_count_note": word_count_note,
        }

    async def generate_essay(
        self,
        payload: EssayGenerateRequest,
        db: AsyncSession,
    ) -> EssayResponse:
        """Executes grounded Ship 30 essay generation and persists the result to PostgreSQL."""
        start_time = time.perf_counter()

        # 1. Resolve Model Provider early to fail-fast on unconfigured cloud credentials (HTTP 503)
        provider_instance, provider_name, model_name = self._resolve_provider(
            requested_provider=payload.provider,
            model_override=payload.model,
        )

        # 2. Resolve or Create ChatSession for persistence
        if payload.session_id:
            session_query = select(ChatSession).where(ChatSession.id == payload.session_id)
            session_res = await db.execute(session_query)
            session_obj = session_res.scalar_one_or_none()
            if not session_obj:
                raise SessionNotFoundError(str(payload.session_id))
        else:
            # Create a dedicated session for this essay
            clean_topic_title = payload.topic[:45] + ("..." if len(payload.topic) > 45 else "")
            session_obj = ChatSession(
                title=f"Essay: {clean_topic_title}",
                provider=provider_name,
                model_name=model_name,
                active_skill="ship30",
                user_metadata={"type": "ship30_essay_thread"},
            )
            db.add(session_obj)
            await db.flush()
            await db.refresh(session_obj)

        # 3. Target Length & Token Budget (Provider-aware: 3,200 for cloud deep-dive, 1,500 for local 8GB RAM)
        desired_len = payload.desired_length or "deep_dive"
        target_words = LENGTH_TARGETS.get(desired_len, 1250)
        max_gen_tokens = get_token_budget(provider_name, desired_len)

        # 4. Transcript Grounding (if enabled)
        evidence_chunks = []
        grounding_context = ""
        citations: List[Dict[str, Any]] = []

        if payload.ground_with_podcasts:
            grounded_evidence: GroundedEvidence = await self.retriever.get_grounded_evidence(
                query=payload.topic,
                db=db,
                top_k=5,
            )
            evidence_chunks = grounded_evidence.chunks
            grounding_context = grounded_evidence.context_text
            citations = grounded_evidence.citations_payload
            logger.info(
                "Retrieved %d transcript chunks for Ship 30 essay on '%s'",
                len(evidence_chunks),
                payload.topic,
            )

        # 5. Construct System & User Prompts
        system_prompt, user_prompt = self._build_essay_prompt(
            topic=payload.topic,
            target_audience=payload.target_audience or "Product Managers, Founders, & Growth Operators",
            tone=payload.tone or "educational",
            desired_length=desired_len,
            target_words=target_words,
            specific_instructions=payload.specific_instructions,
            grounding_context=grounding_context,
            has_evidence=len(evidence_chunks) > 0,
        )

        logger.info(
            "Generating Ship 30 essay via provider '%s' (model: %s, max_tokens: %d)",
            provider_name,
            model_name,
            max_gen_tokens,
        )

        completion: CompletionResult = await provider_instance.generate(
            messages=[ChatMessageInput(role="user", content=user_prompt)],
            system=system_prompt,
            temperature=0.3,
            max_tokens=max_gen_tokens,
        )

        # Bounded structured drafting/expansion:
        # If Cloud Gemini/Anthropic generates < 950 words for a deep-dive essay,
        # perform at most ONE targeted expansion turn to reach ~1,100-1,350 words
        # without introducing uncontrolled loops or excessive API calls.
        # Local Ollama is deliberately skipped to preserve 8 GB RAM performance and stability.
        is_cloud_provider = provider_name.lower() in ("cloud", "gemini", "anthropic")
        if (
            is_cloud_provider
            and desired_len == "deep_dive"
            and len(completion.content.split()) < 950
            and getattr(completion, "finish_reason", "STOP") != "SAFETY"
        ):
            initial_count = len(completion.content.split())
            logger.info(
                "Initial cloud deep-dive draft generated %d words (<950 target). "
                "Triggering single bounded expansion pass.",
                initial_count,
            )
            expansion_prompt = f"""The draft below has established the core structure but requires substantive expansion to reach the full Deep-Dive depth of 1,100–1,350 words (target: ~1,250 words).

<current_draft>
{completion.content}
</current_draft>

EXPANSION INSTRUCTIONS:
1. Retain the headline hook and core 5-pillar Ship 30 structure.
2. Expand each of the 5 pillar sections to ~180–220 words with concrete operational mechanics, counterintuitive growth lessons, and tactical frameworks.
3. Preserve all existing citation markers ([1], [2], etc.) and naturally integrate any remaining podcast evidence. Do not invent fake quotes, timelines, or metrics.
4. End with an exhaustive Tactical Takeaway including a 5-step implementation checklist.
5. Maintain crisp 1-3-1 cadence and high rate of revelation.

Deliver the complete, fully expanded essay now."""

            try:
                expansion_completion: CompletionResult = await provider_instance.generate(
                    messages=[
                        ChatMessageInput(role="user", content=user_prompt),
                        ChatMessageInput(role="assistant", content=completion.content),
                        ChatMessageInput(role="user", content=expansion_prompt),
                    ],
                    system=system_prompt,
                    temperature=0.3,
                    max_tokens=max_gen_tokens,
                )
                if len(expansion_completion.content.split()) > initial_count:
                    completion = expansion_completion
            except Exception as exp_err:
                logger.warning("Bounded essay expansion pass failed; falling back to initial draft: %s", exp_err)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 6. Parse and Analyze Output
        parsed = self._parse_essay_output(
            raw_text=completion.content,
            topic=payload.topic,
            target_words=target_words,
            provider_name=provider_name,
            finish_reason=getattr(completion, "finish_reason", None),
        )

        # 7. Persist in PostgreSQL (Messages & Citations)
        user_message_record = ChatMessage(
            session_id=session_obj.id,
            role="user",
            content=(
                f"Generate a Ship 30 for 30 essay on: {payload.topic}\n"
                f"Target Audience: {payload.target_audience}\n"
                f"Tone: {payload.tone}\n"
                f"Depth: {payload.desired_length} (~{target_words} words)\n"
                f"Podcast Grounding: {'Enabled' if payload.ground_with_podcasts else 'Disabled'}"
            ),
            provider_metadata={"type": "essay_prompt", "topic": payload.topic},
        )
        db.add(user_message_record)
        await db.flush()

        # Metadata bundle for the generated essay
        essay_metadata = {
            "type": "ship30_essay",
            "title": parsed["title"],
            "headline_hook": parsed["headline_hook"],
            "alternative_titles": parsed["alternative_titles"],
            "takeaway": parsed["takeaway"],
            "topic": payload.topic,
            "target_audience": payload.target_audience,
            "tone": payload.tone,
            "desired_length": payload.desired_length,
            "requested_word_count": target_words,
            "actual_word_count": parsed["actual_word_count"],
            "word_count_status": parsed["word_count_status"],
            "word_count_note": parsed["word_count_note"],
            "podcast_grounded": payload.ground_with_podcasts,
            "latency_ms": latency_ms,
            "provider": provider_name,
            "model": model_name,
        }

        assistant_message_record = ChatMessage(
            session_id=session_obj.id,
            role="assistant",
            content=completion.content,
            provider_metadata=essay_metadata,
        )
        db.add(assistant_message_record)
        await db.flush()

        # Persist citations if grounded
        persisted_citations: List[MessageCitation] = []
        for cite_item in citations:
            chunk_uuid = None
            if cite_item.get("chunk_id"):
                try:
                    chunk_uuid = uuid.UUID(str(cite_item["chunk_id"]))
                except (ValueError, TypeError):
                    chunk_uuid = None

            cite_record = MessageCitation(
                message_id=assistant_message_record.id,
                chunk_id=chunk_uuid,
                citation_index=cite_item.get("citation_index", 1),
                episode_id=cite_item.get("episode_id"),
                episode_title=cite_item.get("episode_title"),
                guest_name=cite_item.get("guest_name"),
                timestamp_start=cite_item.get("timestamp_start"),
                timestamp_end=cite_item.get("timestamp_end"),
                quoted_text=cite_item.get("quoted_text") or "",
                relevance_score=cite_item.get("relevance_score"),
            )
            db.add(cite_record)
            persisted_citations.append(cite_record)

        # Touch session timestamp
        session_obj.updated_at = datetime.now(timezone.utc)
        await db.commit()

        await db.refresh(assistant_message_record)

        return EssayResponse(
            id=assistant_message_record.id,
            session_id=session_obj.id,
            title=parsed["title"],
            content=completion.content,
            headline_hook=parsed["headline_hook"],
            alternative_titles=parsed["alternative_titles"],
            takeaway=parsed["takeaway"],
            topic=payload.topic,
            target_audience=payload.target_audience or "Product Managers, Founders, & Growth Operators",
            tone=payload.tone or "educational",
            desired_length=payload.desired_length or "deep_dive",
            requested_word_count=target_words,
            actual_word_count=parsed["actual_word_count"],
            word_count_status=parsed["word_count_status"],
            word_count_note=parsed["word_count_note"],
            provider=provider_name,
            model=model_name,
            latency_ms=latency_ms,
            podcast_grounded=payload.ground_with_podcasts,
            citations=[CitationResponse.model_validate(c) for c in persisted_citations],
            created_at=assistant_message_record.created_at,
        )

    async def get_essay_by_id(
        self,
        essay_id: uuid.UUID,
        db: AsyncSession,
    ) -> Optional[EssayResponse]:
        """Retrieves a previously generated essay by message ID."""
        query = (
            select(ChatMessage)
            .where(ChatMessage.id == essay_id)
            .options(selectinload(ChatMessage.citations))
        )
        res = await db.execute(query)
        msg = res.scalar_one_or_none()
        if not msg:
            return None

        meta = msg.provider_metadata or {}
        if meta.get("type") != "ship30_essay":
            return None

        return EssayResponse(
            id=msg.id,
            session_id=msg.session_id,
            title=meta.get("title", "Generated Essay"),
            content=msg.content,
            headline_hook=meta.get("headline_hook"),
            alternative_titles=meta.get("alternative_titles", []),
            takeaway=meta.get("takeaway"),
            topic=meta.get("topic", ""),
            target_audience=meta.get("target_audience", ""),
            tone=meta.get("tone", "educational"),
            desired_length=meta.get("desired_length", "deep_dive"),
            requested_word_count=meta.get("requested_word_count", 1250),
            actual_word_count=meta.get("actual_word_count", len(msg.content.split())),
            word_count_status=meta.get("word_count_status", "target_achieved"),
            word_count_note=meta.get("word_count_note"),
            provider=meta.get("provider", "ollama"),
            model=meta.get("model", "qwen2.5:1.5b"),
            latency_ms=meta.get("latency_ms", 0.0),
            podcast_grounded=meta.get("podcast_grounded", True),
            citations=[CitationResponse.model_validate(c) for c in msg.citations],
            created_at=msg.created_at,
        )

    async def list_recent_essays(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
    ) -> EssayListResponse:
        """Returns paginated list of generated essays across conversations."""
        query = (
            select(ChatMessage)
            .where(ChatMessage.role == "assistant")
            .order_by(desc(ChatMessage.created_at))
            .options(selectinload(ChatMessage.citations))
            .limit(limit * 2)
        )
        res = await db.execute(query)
        all_msgs = list(res.scalars().all())

        essay_items: List[EssayResponse] = []
        for msg in all_msgs:
            meta = msg.provider_metadata or {}
            if meta.get("type") == "ship30_essay":
                essay_items.append(
                    EssayResponse(
                        id=msg.id,
                        session_id=msg.session_id,
                        title=meta.get("title", "Generated Essay"),
                        content=msg.content,
                        headline_hook=meta.get("headline_hook"),
                        alternative_titles=meta.get("alternative_titles", []),
                        takeaway=meta.get("takeaway"),
                        topic=meta.get("topic", ""),
                        target_audience=meta.get("target_audience", ""),
                        tone=meta.get("tone", "educational"),
                        desired_length=meta.get("desired_length", "deep_dive"),
                        requested_word_count=meta.get("requested_word_count", 1250),
                        actual_word_count=meta.get("actual_word_count", len(msg.content.split())),
                        word_count_status=meta.get("word_count_status", "target_achieved"),
                        word_count_note=meta.get("word_count_note"),
                        provider=meta.get("provider", "ollama"),
                        model=meta.get("model", "qwen2.5:1.5b"),
                        latency_ms=meta.get("latency_ms", 0.0),
                        podcast_grounded=meta.get("podcast_grounded", True),
                        citations=[CitationResponse.model_validate(c) for c in msg.citations],
                        created_at=msg.created_at,
                    )
                )

        paged_items = essay_items[offset : offset + limit]
        return EssayListResponse(items=paged_items, total=len(essay_items))
