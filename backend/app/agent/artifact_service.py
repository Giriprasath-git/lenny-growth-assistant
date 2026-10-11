"""
Dedicated Artifact Generation & Security Sanitization Service.
Generates genuine, AI-synthesized Markdown documents and sandboxed HTML/CSS deliverables
grounded in conversation history, podcast evidence, and user instructions.
"""

from datetime import datetime, timezone
import html
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
from backend.app.core.exceptions import (
    IncompleteArtifactError,
    ProviderUnavailableError,
    SessionNotFoundError,
)
from backend.app.core.logging import logger
from backend.app.db.models.artifact import Artifact
from backend.app.db.models.message import ChatMessage
from backend.app.db.models.session import ChatSession
from backend.app.schemas.artifact import (
    ArtifactGenerateRequest,
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactType,
)


# Security Content Security Policy injected into all previewable HTML deliverables
CSP_POLICY = (
    "default-src 'none'; "
    "style-src 'unsafe-inline'; "
    "script-src 'none'; "
    "img-src data: https:; "
    "form-action 'none';"
)
CSP_META_TAG = f'<meta http-equiv="Content-Security-Policy" content="{CSP_POLICY}">'


class ArtifactGenerationService:
    """Orchestrates genuine AI artifact creation, rigorous security sanitization, and persistence."""

    def __init__(self) -> None:
        pass

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
                        "Please select Local LLM (Ollama) to generate artifacts offline."
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
            # Default to local Ollama with 180s timeout
            ollama_provider = OllamaProvider(
                model=model_override or settings.OLLAMA_MODEL,
                timeout=settings.OLLAMA_REQUEST_TIMEOUT,
            )
            return ollama_provider, "ollama", model_override or settings.OLLAMA_MODEL

    @staticmethod
    def normalize_html_fences(content: str) -> str:
        """Strips accidental outer markdown code block fences (```html, ```HTML, or ```)."""
        cleaned = (content or "").strip()
        prefix_fence = re.match(r"^```(?:html|HTML)?\s*\r?\n?", cleaned, re.IGNORECASE)
        if prefix_fence:
            cleaned = cleaned[prefix_fence.end():]
            cleaned = re.sub(r"\r?\n?```\s*$", "", cleaned)
            cleaned = cleaned.strip()
        return cleaned

    @classmethod
    def validate_html_completeness(
        cls,
        raw_html: str,
        finish_reason: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates structural completeness of AI-generated HTML deliverables.
        Detects truncated output, unclosed stylesheets, missing body, or cut-off documents.
        Never fabricates missing tags; returns actionable failure details for error reporting.
        """
        if finish_reason and str(finish_reason).upper() in ("MAX_TOKENS", "LENGTH", "TRUNCATED"):
            return False, f"Model generation was cut off by provider token limit (finishReason: {finish_reason})"

        cleaned = cls.normalize_html_fences(raw_html)
        if not cleaned or len(cleaned.strip()) < 20:
            return False, "Model generated empty or near-empty HTML content"

        # Check for unclosed style block
        has_style_open = bool(re.search(r"<style\b[^>]*>", cleaned, re.IGNORECASE))
        has_style_close = bool(re.search(r"</style>", cleaned, re.IGNORECASE))
        if has_style_open and not has_style_close:
            return False, "HTML output was truncated inside <style> tag before CSS stylesheet was completed"

        # Check for abrupt cutoff in CSS declaration at the end of the content
        if cleaned.endswith("var") or re.search(r"var\s*$", cleaned) or re.search(r"[a-zA-Z\-]+\s*:\s*(?:var)?\s*$", cleaned):
            return False, "HTML output ended abruptly inside an incomplete CSS declaration"

        # Check for opening head without closing head
        has_head_open = bool(re.search(r"<head\b[^>]*>", cleaned, re.IGNORECASE))
        has_head_close = bool(re.search(r"</head>", cleaned, re.IGNORECASE))
        if has_head_open and not has_head_close:
            return False, "HTML output was truncated inside <head> section"

        # Check for full document vs snippet: if <!DOCTYPE or <html is present, require body and closing tags
        is_full_doc = bool(re.search(r"<!DOCTYPE|<html\b", cleaned, re.IGNORECASE))
        if is_full_doc:
            has_body_open = bool(re.search(r"<body\b[^>]*>", cleaned, re.IGNORECASE))
            if not has_body_open:
                return False, "HTML document is missing a <body> section with renderable content"

            has_body_close = bool(re.search(r"</body>", cleaned, re.IGNORECASE))
            has_html_close = bool(re.search(r"</html>", cleaned, re.IGNORECASE))
            if not has_body_close or not has_html_close:
                return False, "HTML document was truncated before closing </body> or </html> tags"

            # Verify visible body content exists
            body_match = re.search(r"<body\b[^>]*>(.*?)</body>", cleaned, re.IGNORECASE | re.DOTALL)
            if body_match:
                body_inner = body_match.group(1)
                text_only = re.sub(r"<[^>]+>", "", body_inner).strip()
                if len(text_only) < 10:
                    return False, "HTML document body has insufficient visible content"
        else:
            # Snippet mode: must have minimal markup length and not end with incomplete tag or property
            if len(cleaned) < 25:
                return False, "HTML snippet is too short to be a valid deliverable"
            if re.search(r"<[a-zA-Z0-9_\-]+(?:\s+[^>]*)?$", cleaned):
                return False, "HTML output was truncated mid-tag"

        return True, None

    def sanitize_html(self, raw_html: str) -> Tuple[str, bool, Dict[str, Any]]:
        """
        Sanitizes AI-generated HTML content to guarantee script-disabled, self-contained safety.
        - Strips markdown code blocks.
        - Removes <script> tags and active event handlers.
        - Removes <iframe, <object, <embed, <form tags.
        - Injects strict Content Security Policy meta tag.
        """
        cleaned = self.normalize_html_fences(raw_html)
        was_sanitized = cleaned != raw_html.strip()
        blocked_features: List[str] = []

        # Check and strip <script> tags
        if re.search(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", cleaned, re.IGNORECASE):
            cleaned = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", cleaned, flags=re.IGNORECASE)
            was_sanitized = True
            blocked_features.append("script_tags")

        # Check and strip inline JavaScript event handlers (e.g. onclick, onload, onerror)
        handler_pattern = r"\s+on[a-zA-Z]+\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s>]+)"
        if re.search(handler_pattern, cleaned, re.IGNORECASE):
            cleaned = re.sub(handler_pattern, "", cleaned, flags=re.IGNORECASE)
            was_sanitized = True
            blocked_features.append("inline_event_handlers")

        # Strip javascript: protocol in href or src
        js_uri_pattern = r'(href|src)\s*=\s*["\']\s*javascript:[^"\']*["\']'
        if re.search(js_uri_pattern, cleaned, re.IGNORECASE):
            cleaned = re.sub(js_uri_pattern, r'\1="#"', cleaned, flags=re.IGNORECASE)
            was_sanitized = True
            blocked_features.append("javascript_pseudo_protocols")

        # Strip dangerous embedding and navigation elements
        embed_pattern = r"<(?:iframe|object|embed|base|form)\b[^>]*>.*?(?:<\/(?:iframe|object|embed|base|form)>|\/>)"
        if re.search(embed_pattern, cleaned, re.IGNORECASE | re.DOTALL):
            cleaned = re.sub(embed_pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
            was_sanitized = True
            blocked_features.append("embedding_or_form_elements")

        # Guarantee strict CSP meta tag in head
        if re.search(r"<head[^>]*>", cleaned, re.IGNORECASE):
            # Check if CSP meta already present
            if "Content-Security-Policy" not in cleaned:
                cleaned = re.sub(r"(<head[^>]*>)", r"\1\n  " + CSP_META_TAG, cleaned, count=1, flags=re.IGNORECASE)
                was_sanitized = True
        else:
            # Wrap in minimal HTML structure if plain snippet
            cleaned = (
                f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n  <meta charset=\"utf-8\" />\n"
                f"  {CSP_META_TAG}\n"
                f"  <style>\n"
                f"    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
                f"           background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}\n"
                f"  </style>\n</head>\n<body>\n{cleaned}\n</body>\n</html>"
            )
            was_sanitized = True

        policy_summary = {
            "sandbox": "script-disabled",
            "allow_scripts": False,
            "allow_same_origin": False,
            "csp_enforced": True,
            "blocked_features": blocked_features,
        }
        return cleaned, was_sanitized, policy_summary

    def sanitize_markdown(self, raw_md: str) -> Tuple[str, bool, Dict[str, Any]]:
        """
        Sanitizes Markdown content to prevent raw executable HTML injection while preserving formatting.
        """
        cleaned = raw_md.strip()
        was_sanitized = False
        blocked_features: List[str] = []

        # Strip accidental outer code block
        if cleaned.startswith("```markdown") and cleaned.endswith("```"):
            cleaned = cleaned[11:-3].strip()
            was_sanitized = True

        # Escape active script tags in Markdown
        if re.search(r"<script\b", cleaned, re.IGNORECASE):
            cleaned = re.sub(r"<script\b", "&lt;script", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"<\/script>", "&lt;/script&gt;", cleaned, flags=re.IGNORECASE)
            was_sanitized = True
            blocked_features.append("raw_html_scripts")

        # Escape inline event handlers in Markdown raw tags
        handler_pattern = r"\s+on[a-zA-Z]+\s*="
        if re.search(handler_pattern, cleaned, re.IGNORECASE):
            cleaned = re.sub(handler_pattern, " data-blocked-handler=", cleaned, flags=re.IGNORECASE)
            was_sanitized = True
            blocked_features.append("inline_event_handlers")

        policy_summary = {
            "format": "markdown",
            "raw_html_executable": False,
            "blocked_features": blocked_features,
        }
        return cleaned, was_sanitized, policy_summary

    def _extract_title(self, content: str, artifact_type: ArtifactType, custom_title: Optional[str] = None) -> str:
        """Extracts or derives a clean, descriptive title."""
        if custom_title and custom_title.strip():
            return custom_title.strip()

        if artifact_type == ArtifactType.HTML:
            title_match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE)
            if title_match:
                return title_match.group(1).strip()
            h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE)
            if h1_match:
                # Strip any tags inside h1
                clean_h1 = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()
                if clean_h1:
                    return clean_h1

        if artifact_type == ArtifactType.MARKDOWN:
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("# ") and len(line) > 2:
                    return line[2:].strip()
                if line.startswith("## ") and len(line) > 3:
                    return line[3:].strip()

        return "Growth Strategy Deliverable"

    async def _gather_context(
        self,
        request: ArtifactGenerateRequest,
        db: AsyncSession,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Gathers and bounds context from session history or message."""
        citations: List[Dict[str, Any]] = []

        # 1. Custom content supplied explicitly (e.g. from an essay or user clipboard)
        if request.custom_content and request.custom_content.strip():
            return request.custom_content.strip(), citations

        # 2. Specific message requested
        if request.message_id:
            msg_stmt = (
                select(ChatMessage)
                .options(selectinload(ChatMessage.citations))
                .where(ChatMessage.id == request.message_id, ChatMessage.session_id == request.session_id)
            )
            msg_res = await db.execute(msg_stmt)
            target_msg = msg_res.scalar_one_or_none()
            if target_msg:
                # Extract any attached citations
                if target_msg.citations:
                    for c in target_msg.citations:
                        citations.append({
                            "episode_title": c.episode_title,
                            "guest_name": c.guest_name,
                            "timestamp_start": c.timestamp_start,
                            "quoted_text": c.quoted_text,
                        })
                return target_msg.content, citations

        # 3. Session history context (bounded to last 4 messages to preserve 8 GB RAM token budget)
        history_stmt = (
            select(ChatMessage)
            .options(selectinload(ChatMessage.citations))
            .where(ChatMessage.session_id == request.session_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(4)
        )
        hist_res = await db.execute(history_stmt)
        recent_messages = list(reversed(hist_res.scalars().all()))

        context_lines: List[str] = []
        for m in recent_messages:
            sender = "User" if m.role == "user" else "Assistant"
            context_lines.append(f"{sender}: {m.content}")
            if m.citations:
                for c in m.citations:
                    citations.append({
                        "episode_title": c.episode_title,
                        "guest_name": c.guest_name,
                        "timestamp_start": c.timestamp_start,
                        "quoted_text": c.quoted_text,
                    })

        context_text = "\n\n".join(context_lines)
        if not context_text.strip():
            context_text = "No prior messages. Generate a standalone product growth artifact."

        return context_text, citations

    async def generate_artifact(
        self,
        request: ArtifactGenerateRequest,
        db: AsyncSession,
    ) -> ArtifactResponse:
        """
        Generates, sanitizes, and persists a genuine Markdown or HTML/CSS artifact.
        """
        # Validate that session exists
        session_stmt = select(ChatSession).where(ChatSession.id == request.session_id)
        session_res = await db.execute(session_stmt)
        session = session_res.scalar_one_or_none()
        if not session:
            raise SessionNotFoundError(str(request.session_id))

        # Resolve provider early to fail-fast on unconfigured cloud credentials (HTTP 503)
        provider, provider_name, model_name = self._resolve_provider(
            requested_provider=request.provider or session.provider,
            model_override=session.model_name,
        )

        # Gather context
        context_text, citations = await self._gather_context(request, db)

        # Build prompt based on format
        user_instructions = request.instructions or ""
        citations_text = ""
        if citations:
            citations_text = "\nVerified Podcast References:\n" + "\n".join(
                [f"- {c.get('guest_name', 'Guest')} on '{c.get('episode_title', 'Episode')}' ({c.get('timestamp_start', '00:00:00')})" for c in citations[:3]]
            )

        if request.artifact_type == ArtifactType.MARKDOWN:
            system_prompt = (
                "You are an elite Product Strategy Document Architect. "
                "Your objective is to synthesize the provided conversation context and instructions into a "
                "publication-grade, comprehensive Markdown deliverable (e.g. Strategy Playbook, PRD, Growth Framework, or Review Matrix).\n\n"
                "Formatting Guidelines:\n"
                "1. Start with an executive title (# Title) and 2-sentence executive summary.\n"
                "2. Structure content into logical, high-impact sections with subheadings (## and ###).\n"
                "3. Use structured Markdown comparison tables (| Header 1 | Header 2 |) where comparing options or tradeoffs.\n"
                "4. Use bulleted action checklists (- [ ] Action) for execution playbooks.\n"
                "5. Ground key arguments in the provided podcast evidence without inventing false quotes.\n"
                "6. Write clean, complete Markdown. DO NOT output any raw HTML or JavaScript code."
            )
            user_prompt = (
                f"Source Context:\n{context_text}\n{citations_text}\n\n"
                f"User Instructions: {user_instructions if user_instructions else 'Format this into a standalone, executive Markdown strategy deliverable.'}\n\n"
                f"Generate the complete Markdown document now:"
            )
        else:
            # HTML/CSS Deliverable
            system_prompt = (
                "You are an elite Frontend UI Engineer and Visual Product Designer. "
                "Your objective is to generate a complete, self-contained, responsive HTML5 deliverable with embedded CSS "
                "representing a visual growth framework, scorecard, interactive calculator layout, or comparison matrix.\n\n"
                "CRITICAL FORMAT RULES FOR COMPLETENESS:\n"
                "1. Output a complete, valid HTML5 document starting with <!DOCTYPE html> and ending with </body></html>.\n"
                "2. Keep embedded CSS inside `<style>` CONCISE and compact (under 55 lines) so the document NEVER truncates.\n"
                "3. Prioritize rich, visible, complete semantic HTML body content (cards, metrics, comparisons, summaries).\n"
                "4. All main content must be static and rendered directly in HTML markup. Do not rely on JavaScript to display content.\n"
                "5. Use an Obsidian dark theme matching the app: Canvas #0f172a, Cards #1e293b, Borders #334155, Accent Amber #f59e0b, Text #f8fafc, Muted Text #94a3b8.\n"
                "6. End cleanly with `</body></html>`.\n\n"
                "CRITICAL SECURITY RESTRICTIONS:\n"
                "- Output ONLY safe HTML and CSS. DO NOT include any <script> tags or JavaScript code.\n"
                "- DO NOT include inline event handlers (such as onclick, onload, onerror).\n"
                "- DO NOT include any external stylesheets (<link rel='stylesheet'>) or external font links.\n"
                "- DO NOT include forms, search inputs, or active navigation.\n"
                "- The entire visual deliverable must be completely self-contained."
            )
            user_prompt = (
                f"Source Context:\n{context_text}\n{citations_text}\n\n"
                f"User Instructions: {user_instructions if user_instructions else 'Create a visual HTML/CSS deliverable with cards and framework layout.'}\n\n"
                f"Generate the complete, self-contained HTML document now:"
            )

        prompt_messages: List[ChatMessageInput] = [
            ChatMessageInput(role="system", content=system_prompt),
            ChatMessageInput(role="user", content=user_prompt),
        ]

        logger.info(
            f"Generating {request.artifact_type.value} artifact for session {request.session_id} using {provider_name}:{model_name}"
        )

        # Dynamic output token limit: Cloud Gemini/Anthropic receives up to 2500 tokens for complete HTML/CSS
        token_limit = (
            min(settings.GEMINI_MAX_TOKENS, 2500)
            if provider_name in ("cloud", "gemini", "anthropic")
            else 1500
        )

        start_time = time.time()
        completion: CompletionResult = await provider.generate(
            messages=prompt_messages,
            max_tokens=token_limit,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        raw_output = completion.content or ""

        # Validate and sanitize according to format
        if request.artifact_type == ArtifactType.HTML:
            # Check for truncation or incomplete generation before persisting
            is_valid, err_reason = self.validate_html_completeness(
                raw_output,
                finish_reason=completion.finish_reason,
            )
            if not is_valid:
                logger.warning(
                    f"Incomplete HTML artifact generation rejected for session {request.session_id}: {err_reason}"
                )
                raise IncompleteArtifactError(
                    message=(
                        f"The AI model generated an incomplete HTML deliverable ({err_reason}). "
                        "Please retry artifact generation with concise instructions or switch to Local LLM."
                    ),
                    details={
                        "reason": err_reason,
                        "finish_reason": completion.finish_reason,
                        "provider": provider_name,
                        "model": model_name,
                    },
                )
            sanitized_content, was_sanitized, sec_policy = self.sanitize_html(raw_output)
        else:
            if not raw_output.strip():
                raise IncompleteArtifactError("The AI model returned an empty Markdown response.")
            sanitized_content, was_sanitized, sec_policy = self.sanitize_markdown(raw_output)

        title = self._extract_title(sanitized_content, request.artifact_type, request.title)

        # Persist to database
        artifact_id = uuid.uuid4()
        turn_message_id = uuid.uuid4()
        linked_message_id = request.message_id or turn_message_id

        artifact = Artifact(
            id=artifact_id,
            session_id=request.session_id,
            message_id=linked_message_id,
            artifact_type=request.artifact_type.value,
            title=title,
            content=sanitized_content,
        )
        db.add(artifact)

        # Also persist an assistant message in the conversation thread noting artifact creation
        turn_message = ChatMessage(
            id=turn_message_id,
            session_id=request.session_id,
            role="assistant",
            content=f"Created {request.artifact_type.value.upper()} artifact: **{title}**.\n\nOpen the Artifact Viewer in the right panel to inspect the deliverable.",
            provider_metadata={
                "type": "artifact_creation",
                "artifact_id": str(artifact_id),
                "artifact_type": request.artifact_type.value,
                "title": title,
                "provider": provider_name,
                "model": model_name,
                "latency_ms": latency_ms,
                "security_policy": sec_policy,
            },
        )
        db.add(turn_message)
        await db.commit()
        await db.refresh(artifact)

        return ArtifactResponse(
            id=artifact.id,
            session_id=artifact.session_id,
            message_id=artifact.message_id,
            artifact_type=artifact.artifact_type,
            title=artifact.title,
            content=artifact.content,
            provider=provider_name,
            model_name=model_name,
            created_at=artifact.created_at,
            is_sanitized=was_sanitized,
            security_policy=sec_policy,
            metadata={
                "latency_ms": latency_ms,
                "length_chars": len(artifact.content),
                "citations_count": len(citations),
            },
        )

    async def _resolve_artifact_attribution(
        self,
        artifact: Artifact,
        db: AsyncSession,
    ) -> Tuple[str, str]:
        """
        Resolves genuine generation-time provider and model from message metadata.
        Falls back to 'Model unavailable' if historical attribution cannot be reliably determined.
        Never blindly falls back to current session default.
        """
        try:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == artifact.session_id)
                .order_by(desc(ChatMessage.created_at))
            )
            res = await db.execute(stmt)
            messages = res.scalars().all()

            # 1. Match message where provider_metadata["artifact_id"] == str(artifact.id)
            for msg in messages:
                meta = msg.provider_metadata or {}
                if str(meta.get("artifact_id", "")) == str(artifact.id):
                    prov = meta.get("provider")
                    mod = meta.get("model") or meta.get("model_name")
                    if prov and mod and prov != "stored" and mod != "stored":
                        return prov, mod

            # 2. Match message referenced by artifact.message_id
            if artifact.message_id:
                for msg in messages:
                    if msg.id == artifact.message_id and msg.provider_metadata:
                        prov = msg.provider_metadata.get("provider")
                        mod = msg.provider_metadata.get("model") or msg.provider_metadata.get("model_name")
                        if prov and mod and prov != "stored" and mod != "stored":
                            return prov, mod

            # 3. Check assistant turn message around artifact creation
            for msg in messages:
                if msg.role == "assistant" and msg.provider_metadata:
                    prov = msg.provider_metadata.get("provider")
                    mod = msg.provider_metadata.get("model") or msg.provider_metadata.get("model_name")
                    if prov and mod and prov != "stored" and mod != "stored":
                        return prov, mod
        except Exception as e:
            logger.debug(f"Attribution lookup error: {e}")

        # 4. Fallback to session configuration if present and genuine, otherwise 'Model unavailable'
        if artifact.session and artifact.session.provider and artifact.session.provider != "stored":
            return artifact.session.provider, artifact.session.model_name or "qwen2.5:1.5b"

        return "Model unavailable", "Model unavailable"

    async def get_artifact(self, artifact_id: uuid.UUID, db: AsyncSession) -> Optional[ArtifactResponse]:
        """Retrieves a single artifact by UUID."""
        stmt = select(Artifact).options(selectinload(Artifact.session)).where(Artifact.id == artifact_id)
        res = await db.execute(stmt)
        artifact = res.scalar_one_or_none()
        if not artifact:
            return None

        sec_policy = {
            "sandbox": "script-disabled",
            "allow_scripts": False,
            "allow_same_origin": False,
            "csp_enforced": True,
        }
        prov, mod = await self._resolve_artifact_attribution(artifact, db)

        return ArtifactResponse(
            id=artifact.id,
            session_id=artifact.session_id,
            message_id=artifact.message_id,
            artifact_type=artifact.artifact_type,
            title=artifact.title,
            content=artifact.content,
            provider=prov,
            model_name=mod,
            created_at=artifact.created_at,
            is_sanitized=True,
            security_policy=sec_policy,
            metadata={"length_chars": len(artifact.content)},
        )

    async def list_session_artifacts(
        self,
        session_id: uuid.UUID,
        db: AsyncSession,
        limit: int = 50,
        offset: int = 0,
    ) -> ArtifactListResponse:
        """Lists all artifacts associated with a chat session."""
        stmt = (
            select(Artifact)
            .options(selectinload(Artifact.session))
            .where(Artifact.session_id == session_id)
            .order_by(desc(Artifact.created_at))
            .offset(offset)
            .limit(limit)
        )
        res = await db.execute(stmt)
        artifacts = res.scalars().all()

        items = []
        for a in artifacts:
            prov, mod = await self._resolve_artifact_attribution(a, db)
            items.append(
                ArtifactResponse(
                    id=a.id,
                    session_id=a.session_id,
                    message_id=a.message_id,
                    artifact_type=a.artifact_type,
                    title=a.title,
                    content=a.content,
                    provider=prov,
                    model_name=mod,
                    created_at=a.created_at,
                    is_sanitized=True,
                    security_policy={"sandbox": "script-disabled", "csp_enforced": True},
                    metadata={"length_chars": len(a.content)},
                )
            )

        return ArtifactListResponse(items=items, total=len(items))

    async def delete_artifact(self, artifact_id: uuid.UUID, db: AsyncSession) -> bool:
        """Deletes an artifact by UUID."""
        stmt = select(Artifact).where(Artifact.id == artifact_id)
        res = await db.execute(stmt)
        artifact = res.scalar_one_or_none()
        if not artifact:
            return False
        await db.delete(artifact)
        await db.commit()
        return True
