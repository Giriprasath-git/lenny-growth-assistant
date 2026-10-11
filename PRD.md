# Product Requirements Document (PRD)
## The Lenny Growth Assistant

**Document Status:** Final Application Stabilization, Dockerized & Submission Ready  
**Project:** The Lenny Growth Assistant  
**Author:** Forward Deployed AI Systems Architect (Oogway Labs)  
**Target Delivery:** Two-Day Forward Deployed Engineer Take-Home Technical Assessment  

---

## 1. Executive Summary & Problem Statement

Product Managers, Growth Practitioners, and Founders constantly struggle with high-friction discovery of tactical advice. While *Lenny's Podcast* contains hundreds of hours of world-class, battle-tested interviews with top product leaders (e.g., Brian Chesky, Shreyas Doshi, Elena Verna, Gustaf Alströmer), accessing this institutional knowledge is cumbersome:
- Traditional podcast players offer no contextual semantic search.
- Generic LLMs hallucinate generalities rather than referencing Lenny's specific guest frameworks.
- Growth leaders need structured, actionable outputs (such as Atomic Essays, growth loop diagrams, teardowns, and execution checklists) rather than walls of unstructured text.

**The Lenny Growth Assistant** is an AI conversational intelligence application grounded in Lenny's Podcast transcripts. It provides grounded synthesis with direct source citations (guest name, episode title, timestamp, exact quote), multi-turn chat sessions with persistent memory, a dedicated writing skill inspired by the *Ship 30 for 30* methodology for viral atomic communication, and an interactive, safely sandboxed Artifact Viewer for rich HTML/CSS and Markdown deliverables.

---

## 2. Target Users & Personas

| Persona | Primary Goal | Core Frustration |
| :--- | :--- | :--- |
| **Product Manager (Mid-to-Senior)** | Validate roadmaps, feature prioritization, and retention models against top tech company playbooks. | Generic advice lacks context on B2B vs. B2C nuances discussed by Lenny's guests. |
| **Growth Lead / Founder** | Design acquisition loops, pricing tiers, and viral mechanics. | Searching through hours of audio/video for specific strategies is impossible during active sprint planning. |
| **Content Creator / Operator** | Synthesize insights into crisp, readable posts and memos using proven structures. | Raw LLM output is fluffy, verbose, and difficult to share with teams. |

---

## 3. Performance & Success Metrics (Target Hypotheses vs. Empirical Validation)

> **Architectural Note on Performance:** The figures below represent **preliminary target design hypotheses** for the system architecture. In an 8 GB RAM Windows development environment, actual performance is subject to host thread scheduling, local model quantization (Q4_K_M), disk I/O, and external network conditions. Final measured performance benchmarks will be formally captured and validated during Phase 6 testing and evaluation.

1. **Grounded Retrieval Quality (Target Goal):**
   - Target $\ge 90\%$ of growth recommendations citing at least one verified episode timestamp and guest quote.
   - Zero unsourced claims on factual guest anecdotes within verified transcript corpus.
2. **Retrieval Latency (Proposed Design Target):**
   - Target goal: Sub-2.0 seconds for hybrid vector search across transcript chunks (subject to empirical measurement).
3. **Time to First Token (TTFT - Proposed Design Target):**
   - Cloud LLM: Target $< 1.5 - 2.0\text{ seconds}$ TTFT over HTTPS (dependent on provider API latency).
   - Local Ollama (Quantized 3B on 8 GB RAM): Target $< 3.5\text{ seconds}$ TTFT under standard CPU/GPU offload.
4. **Hardware Footprint (Strict Operational Constraint):**
   - Peak process memory budget $\le 6.5\text{ GB}$ total to leave $\ge 1.5\text{ GB}$ buffer for the Windows OS and prevent memory thrashing.
5. **Session Continuity & Integrity:**
   - $100\%$ persistence of user conversation histories, message citations, and generated artifacts in PostgreSQL.
6. **Artifact Isolation:**
   - Zero script execution by default for static HTML/CSS artifacts; opaque null-origin boundary with zero parent frame access.

---

## 4. Assumptions & Constraints

### 4.1 System & Hardware Assumptions
- **Host System:** Windows OS, strictly 8 GB Total System RAM, limited free storage on root `C:` drive.
- **Project Root:** All code, virtual environments, indices, and data storage must reside exclusively on the secondary workspace drive (`D:/OogwayLabs/LennyGrowthAssistant`).
- **PostgreSQL Database:** Locally available or lightweight containerized PostgreSQL 15+ instance with `pgvector` extension enabled.

### 4.2 Technology & Model Assumptions
- **Agent Framework & Pi Coding Agent SDK:** Verified integration of the official `@earendil-works/pi-coding-agent: 1.1.0` SDK running in an isolated Node.js/TypeScript daemon on loopback, enforcing read-only safe tool boundaries without arbitrary execution.
- **Dual-Model Switching Architecture:**
  - **Local Development Default:** Local Ollama running `qwen2.5:1.5b` over HTTP API with a configurable 180s timeout optimized for CPU inference on 8 GB RAM machines.
  - **Cloud LLM Mode:** Official Google Gemini REST API integrating `gemini-3.5-flash-lite` (free-tier eligible) without external heavyweight SDK dependencies. Legacy Anthropic provider preserved.
- **Dockerized Evaluator Deployment:** Fully containerized multi-service deployment via Docker Compose running on non-conflicting host ports (Frontend: 8080, Backend: 8001), isolated PostgreSQL volume, and zero disruption to the host's existing database.
- **Repository & Version Control Policy:** All required public assessment documentation (`PRD.md`, `architecture.md`, `design.md`, `README.md`, `docs/`) and sanitized agent transcripts/evaluations are tracked for GitHub publication. Internal developer notes, raw private logs, and `private-docs/` remain strictly excluded via `.gitignore`.

---

## 5. Scope

### In-Scope (Planned Across Development Phases)
- **Phase 1 (Current):** Architectural blueprint, folder scaffolding, API contracts, TypeScript definitions, database models, environment configurations, and core documentation.
- **Phase 2 (Ingestion & Storage):** Transcript data acquisition pipeline, speaker-aware chunking, vector embedding, and PostgreSQL + pgvector schema migrations.
- **Phase 3 (RAG & Agent Core):** Hybrid semantic search, Anthropic Claude Agent SDK / Pi Coding Agent integration, Ollama provider adapter, and Ship 30 for 30 writing skill engine.
- **Phase 4 (API & Streaming):** FastAPI asynchronous endpoints, Server-Sent Events (SSE) streaming, citation resolution, and session management.
- **Phase 5 (Frontend Experience):** Modern React + Vite UI, Dark-mode theme, citation inspector drawer, and secure HTML/CSS/Markdown Artifact sandbox.
- **Phase 6 (Testing & Hardening):** Unit and integration test suites, structured logging, empirical latency/memory profiling, sanitized agent transcript generation, and resilient error recovery.

### Out-of-Scope
- Voice-to-text live audio transcription (pre-transcribed podcast texts will be ingested).
- User authentication and multi-tenant authorization (single-user / local assessment workspace).
- Third-party social media publishing automation.

---

## 6. Detailed Feature Requirements & Acceptance Criteria

### 6.1 Conversational Chat Interface & Session Persistence
- **AC 1.1:** Users can initiate new conversations, review chat history, and delete old sessions.
- **AC 1.2:** All sessions, user queries, assistant messages, and citations must persist in PostgreSQL.
- **AC 1.3:** Streaming responses provide continuous visual feedback (typing indicator, token stream).

### 6.2 Grounded Transcript Retrieval & Citations
- **AC 2.1:** Every assistant answer citing advice must provide inline clickable citation badges (e.g., `[1] Shreyas Doshi - Episode #42 (12:45)`).
- **AC 2.2:** Clicking a citation opens a drawer or tooltip displaying the verbatim transcript excerpt, timestamp, episode title, and speaker name.
- **AC 2.3:** If a query cannot be answered using the transcript corpus, the assistant must explicitly state that the topic is not covered in Lenny's podcast archives.

### 6.3 Dedicated "Ship 30 for 30" Writing Skill
- **AC 3.1:** Users can trigger or toggle the Ship 30 for 30 skill (e.g., via prompt instruction or UI toggle).
- **AC 3.2:** When enabled, the output must generate a comprehensive, deeply structured essay of **approximately 1,250 words** adhering to Cole & Ship 30 formatting principles:
  - Compelling, benefit-driven headline.
  - Multi-section essay structure (4-6 actionable pillars/playbooks), without imposing a 300-word limit.
  - 1-3-1 sentence rhythm and scannable visual pacing throughout subsections.
  - High Rate of Revelation with zero corporate preamble or fluff.
  - Dense integration of verified, timestamped citations from Lenny's guests.

### 6.4 Secure Artifact Viewer (Markdown & HTML/CSS)
- **AC 4.1:** When the assistant produces HTML/CSS components (e.g., landing page mockups, tables, growth models), they are rendered inside an isolated iframe sandbox.
- **AC 4.2:** **Favor Script-Disabled Sandboxing:** Static HTML/CSS artifacts must render with scripts strictly disabled (`sandbox=""` or omitting `allow-scripts`) and a restrictive CSP header (`script-src 'none'`).
- **AC 4.3:** **No Same-Origin Access:** The iframe must omit `allow-same-origin` in all modes, enforcing opaque null-origin execution to guarantee that parent DOM, cookies, and local storage cannot be accessed.
- **AC 4.4:** Markdown artifacts render with syntax highlighting and copy-to-clipboard functionality.

### 6.5 Reproducible Dockerized Evaluator Deployment
- **AC 5.1:** Evaluator can launch the entire system with `docker compose up --build -d` without conflicting with local development ports (Frontend runs on 8080, Backend runs on 8001).
- **AC 5.2:** Docker database runs in an isolated named volume (`lenny_postgres_data`) without mounting, touching, or migrating the host machine's existing PostgreSQL database.
- **AC 5.3:** Containers communicate reliably with Ollama on the Windows host via `host.docker.internal:11434` without duplicating model weights inside images.
- **AC 5.4:** Real `@earendil-works/pi-coding-agent: 1.1.0` SDK daemon runs in an isolated container environment with read-only tools and healthy liveness checks.

---

## 7. Key Technical Risks & Mitigations

| Risk | Impact | Probability | Architectural Mitigation |
| :--- | :--- | :--- | :--- |
| **8 GB RAM Exhaustion on Windows** | High | High | • Use lightweight quantized models (`llama3.2:3b` ~2.0 GB VRAM/RAM).<br>• Rely on PostgreSQL `pgvector` rather than hosting dedicated standalone vector DB instances.<br>• Implement streaming responses to avoid memory buffers. |
| **C: Drive Space Depletion** | High | Medium | • Ensure all project dependencies, virtual environments, and data caches are anchored on `D:/OogwayLabs/LennyGrowthAssistant`. |
| **Model Hallucination / Unsourced Claims** | Medium | Medium | • System prompt enforces strict retrieval bounding.<br>• Grounded citations injected directly into the prompt context with source IDs. |
| **Malicious or Broken Artifact Code Injection** | High | Low | • Sandboxed iframe execution policy (`sandbox="allow-scripts"` without `allow-same-origin`).<br>• Content Security Policy headers preventing unauthorized external network requests from within the sandbox. |
| **Local LLM Latency & Inconsistent Tool Use** | Medium | Medium | • Clean provider adapter layer: fallback between Cloud (Claude 3.5) and local Ollama.<br>• Simple schema design compatible with smaller model parameter sizes. |
