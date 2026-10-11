# The Lenny Growth Assistant

An AI-powered conversational intelligence platform grounded in transcripts from **Lenny's Podcast**. Built for Product Managers, Growth Leads, and Founders, it provides grounded product management and growth recommendations, direct timestamped citations, an integrated **Ship 30 for 30** writing engine, and a secure, sandboxed artifact viewer for interactive deliverables.

---

## 🚀 Key Capabilities

- **Grounded Wisdom & Verifiable Citations:** Every recommendation references Lenny's interview archives (e.g., Shreyas Doshi, Elena Verna, Brian Chesky) with episode titles, timestamps, and quotes.
- **Grounded Wisdom & Verifiable Citations:** Every recommendation references Lenny's interview archives (e.g., Shreyas Doshi, Elena Verna, Brian Chesky) with episode titles, timestamps, and quotes.
- **Local-First AI & Dual Model Toggle (Local Ollama / Cloud Gemini):** Local Ollama running `qwen2.5:1.5b` over HTTP API is the development default with configurable 180s timeout tuned for CPU inference. Cloud mode integrates Google Gemini (`gemini-3.5-flash-lite`) via REST API without SDK dependencies. Free-tier availability and quotas depend on the user's Google AI account. No cloud API key is required for local Ollama development or mocked test execution (the user will be notified when a key is needed for live cloud verification). Legacy Anthropic provider is preserved.
- **Coding-Agent SDK Architecture & Audit:** Isolated provider-neutral boundaries for Claude Agent SDK and Pi Coding Agent with explicit audit tracking; offline deterministic pre-retrieval grounding enables reliable reasoning on an 8 GB RAM laptop without unsupported multi-turn tool calling failures (SDK requirement tracked for Phase 4C compliance).
- **Ship 30 for 30 Writing Engine:** Synthesize strategic playbooks into comprehensive, high-leverage essays of **approximately 1,250 words** featuring hook-driven headlines, multi-section frameworks, and 1-3-1 visual pacing.
- **Secure Sandboxed Artifact Viewer:** Renders generated HTML/CSS deliverables with **script-disabled sandboxing favored by default** for static components, restrictive CSP (`script-src 'none'`), and zero same-origin access.
- **8 GB RAM Host Target:** Designed specifically for Windows machines with 8 GB RAM, consolidating vector search and session persistence in a single PostgreSQL instance using `pgvector`.
- **D: Drive Workspace Isolation:** All code, dependencies, and vector data reside strictly on Drive D:, safeguarding primary system drive capacity.
- **Corpus Integrity & Tracking:** 272 unique episodes and 8,504 transcript chunks indexed; deferred duplicate episode ID issue P3-D01 remains unresolved and tracked.

---

## 🛠️ Technology Stack

| Layer | Technology | Rationale |
| :--- | :--- | :--- |
| **Frontend** | React 18 + Vite (TypeScript) | Fast startup, native ES modules, low dev memory footprint. |
| **Styling** | Vanilla CSS Design Tokens | High-craft, bespoke dark theme without heavyweight CSS framework overhead. |
| **Backend API** | Python 3.11+ FastAPI + Uvicorn | Asynchronous, high-throughput, native Server-Sent Events (SSE) streaming. |
| **Persistence & Vectors** | PostgreSQL 15+ with `pgvector` | Unified relational and vector database; eliminates the RAM overhead of a separate vector server. |
| **Agent Framework** | Claude Agent SDK / Pi Coding Agent Boundaries | Isolated provider-neutral boundaries; deterministic grounding loop for local development; full SDK requirement tracked. |
| **Default Local LLM** | Ollama (`qwen2.5:1.5b`) | Local-first out-of-process HTTP API, 180s configurable timeout, zero cloud credentials required, tuned for 8 GB RAM. |
| **Cloud LLM (Free-Tier)** | Google Gemini (`gemini-3.5-flash-lite`) | Documented cloud provider via official REST API (`httpx`); free-tier availability and quotas depend on user account tier; startup succeeds cleanly without API keys. |
| **Legacy Cloud LLM** | Anthropic Claude (Configurable) | Optional legacy cloud provider; backward compatible. |
| **Sandboxing** | HTML5 Iframe (Script-disabled default; opaque null-origin) | Strict origin isolation protecting the parent application from untrusted script execution. |

---

## 📁 Project Directory Structure

```
d:/OogwayLabs/LennyGrowthAssistant/
├── backend/                  # Python FastAPI Backend
│   ├── app/
│   │   ├── main.py           # Application entrypoint & CORS
│   │   ├── core/             # Configuration, logging, exceptions
│   │   ├── api/v1/           # Modular endpoints (health, chat, transcripts)
│   │   ├── db/               # PostgreSQL engine, session, & SQLAlchemy models
│   │   ├── rag/              # Ingestion, embeddings, & vector retrieval
│   │   └── agent/            # Orchestrator, provider adapters, & Ship 30 skill
│   ├── requirements.txt      # Backend Python dependencies
│   └── pyproject.toml        # Package & build definitions
├── frontend/                 # React + Vite Frontend
│   ├── src/
│   │   ├── main.tsx          # Application entrypoint
│   │   ├── App.tsx           # Layout & active workspace state
│   │   ├── styles/           # Vanilla CSS design tokens & components
│   │   ├── components/       # Layout, chat, & artifact viewer components
│   │   ├── services/         # API & SSE streaming client
│   │   └── types/            # TypeScript interfaces
│   ├── index.html            # Main HTML document
│   ├── vite.config.ts        # Vite build & proxy configuration
│   └── package.json          # Node dependencies & scripts
├── ingestion/                # Transcript ingestion & preprocessing scripts
├── data/                     # Local storage for transcript archives & cache
├── agent_transcripts/        # Authentic coding-agent execution traces & session audits
├── tests/                    # Backend & frontend test suites
├── private-docs/             # Local planning records & agile work logs (git-ignored)
├── PRD.md                    # Product Requirements Document
├── architecture.md           # System Architecture & Hardware Allocation
├── design.md                 # UI/UX Specifications & API Contracts
├── .env.example              # Environment variable template
└── .gitignore                # Version control exclusions
```

---

## ⚙️ Manual Execution & Verification Guide (For User Manual Run)

> **Execution Restriction Notice:** Per strict development protocol, no terminal commands, migrations, server processes, or tests have been executed by the agent. All backend code, models, migration scripts, and test suites have been prepared and are ready for manual execution below.

### 1. Backend Environment Setup
```powershell
# Navigate to backend directory
cd D:\OogwayLabs\LennyGrowthAssistant\backend

# Create virtual environment on D: drive
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r requirements.txt

# Copy environment variables template
cp ..\.env.example ..\.env
```

### 2. Apply Database Migrations (Manual)
Ensure PostgreSQL 15+ is running with `pgvector` and the `lenny_assistant` database exists:
```powershell
# Navigate to backend directory with virtual environment activated
cd D:\OogwayLabs\LennyGrowthAssistant\backend

# Execute the prepared Phase 2 migration
alembic upgrade head
```

### 3. Run Automated Tests (Manual)
The test suite utilizes in-memory SQLite and isolated mock fixtures (zero dependency on running PostgreSQL):
```powershell
# Run all backend and ingestion tests
cd D:\OogwayLabs\LennyGrowthAssistant
pytest tests/backend tests/ingestion -v

# Or run ingestion suite specifically
pytest tests/ingestion -v
```

### 4. Transcript Ingestion & Knowledge Base Preparation (Phase 3 – Step 3A)

#### A. Download Transcript Dataset (Manual Step)
Download or clone the verified ChatPRD repository:
```powershell
# Repository: https://github.com/ChatPRD/lennys-podcast-transcripts
# Destination: D:\OogwayLabs\LennyGrowthAssistant\data\raw_transcripts
git clone https://github.com/ChatPRD/lennys-podcast-transcripts.git D:\OogwayLabs\LennyGrowthAssistant\data\raw_transcripts
```
*Note: The raw transcript files remain strictly local and are excluded by `.gitignore` to protect intellectual property and attribution.*

#### B. Dry-Run Parse Validation
Validate Markdown frontmatter, speaker turn extraction, and chunk formatting without writing to PostgreSQL:
```powershell
cd D:\OogwayLabs\LennyGrowthAssistant
python ingestion/run_ingestion.py --data-dir data/raw_transcripts --dry-run --limit 5
```

#### C. Full Database Ingestion
Ingest transcript chunks into PostgreSQL with automatic content hashing, duplicate prevention, and batching:
```powershell
cd D:\OogwayLabs\LennyGrowthAssistant
python ingestion/run_ingestion.py --data-dir data/raw_transcripts --batch-size 50
```

### 5. Running the Development Servers (Manual)
```powershell
# Terminal 1 - Backend API:
cd D:\OogwayLabs\LennyGrowthAssistant\backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 - Frontend Dev Server:
cd D:\OogwayLabs\LennyGrowthAssistant\frontend
npm install
npm run dev
```

### 6. API Verification Endpoints
Once Uvicorn is running, verify the endpoints via Swagger UI at `http://127.0.0.1:8000/docs`:
- `GET /api/v1/health/live` - Process liveness (returns HTTP 200 `{"status": "alive"}`).
- `GET /api/v1/health/ready` - Database readiness (returns HTTP 200 if connected, HTTP 503 if DB down).
- `GET /api/v1/health` - Diagnostics, memory metrics, provider config, and database connection status.
- `POST /api/v1/sessions` - Create chat session.
- `GET /api/v1/sessions` - List chat sessions with pagination (`limit`, `offset`).
- `GET /api/v1/sessions/{session_id}` - Retrieve session with chronological messages and citations.
- `DELETE /api/v1/sessions/{session_id}` - Delete session (cascades to all associated messages).
- `POST /api/v1/sessions/{session_id}/messages` - Append a message to an active session.
- `POST /api/v1/transcripts/search` - Grounded multi-signal transcript search with relevance ranking, source excerpts, and deep YouTube timestamp citations (Step 3B).
- `GET /api/v1/transcripts/status` - Transcript corpus indexing metrics (indexed episodes, total chunks, retrieval mode).
- `POST /api/v1/chat` - Grounded AI conversation turn (Step 4A): retrieves evidence, invokes local Ollama (`qwen2.5:1.5b`), and transactionally persists messages and citations.
- `POST /api/v1/chat/agent` - Grounded AI conversation turn explicitly powered by the real `@earendil-works/pi-coding-agent` SDK microservice (Phase 4C).
- `POST /api/v1/chat/message` - Alias endpoint for grounded conversation turns.
- `POST /api/v1/chat/essay` - Alias endpoint for Ship 30 essay generation.
- `POST /api/v1/essays` - Grounded Ship 30 for 30 essay generation (Phase 6): generates structured short-form nonfiction essays with atomic hooks, 1-3-1 cadence, takeaway frameworks, and podcast citations.
- `POST /api/v1/essays/generate` - Alias endpoint for essay generation.
- `GET /api/v1/essays` - List recently generated essays with word counts, tone, provider, and linked citation counts.
- `GET /api/v1/essays/{essay_id}` - Retrieve a generated essay by ID.
- `POST /api/v1/artifacts` - AI-powered Artifact Generation (Phase 7): synthesizes publication-grade Markdown strategy documents or self-contained HTML/CSS deliverables grounded in conversation history.
- `POST /api/v1/artifacts/generate` - Alias endpoint for artifact generation.
- `GET /api/v1/artifacts/{artifact_id}` - Retrieve an artifact by ID.
- `GET /api/v1/artifacts?session_id={id}` - List all artifacts belonging to a conversation session.
- `GET /api/v1/sessions/{session_id}/artifacts` - List session artifacts.
- `GET /api/v1/artifacts/{artifact_id}/download` - Securely download an artifact as `.md` or `.html` with attachment disposition headers.
- `DELETE /api/v1/artifacts/{artifact_id}` - Delete an artifact.
- `GET /api/v1/chat/sdk-status` - Coding-agent SDK compatibility and model provider diagnostic status (includes live Pi SDK service probe).

### 7. Pi Coding Agent SDK Microservice Setup (`pi-agent-service`)
The application features a real integration with the official `@earendil-works/pi-coding-agent: 1.1.0` SDK running in an isolated Node.js/TypeScript bridge microservice on loopback (`http://127.0.0.1:8765`), utilizing the modern `ModelRuntime` API (`ModelRuntime.create({ modelsPath })` and `modelRuntime.getModel()`).

#### A. Install Service Dependencies (User Manual Run)
```powershell
cd D:\OogwayLabs\LennyGrowthAssistant\pi-agent-service
npm install
```

#### B. Start SDK Bridge Service
```powershell
cd D:\OogwayLabs\LennyGrowthAssistant\pi-agent-service
npm run dev
```
The service will start on `http://127.0.0.1:8765` and connect to local Ollama at `http://127.0.0.1:11434/v1`.

#### C. Manual Verification Commands (cURL / PowerShell)

1. **Verify SDK Service Health & Status:**
```powershell
# Probe Node.js bridge service directly
curl.exe http://127.0.0.1:8765/health

# Probe via FastAPI SDK diagnostics endpoint
curl.exe http://127.0.0.1:8000/api/v1/chat/sdk-status
```

2. **Execute Grounded Turn via Pi Coding Agent SDK (`POST /api/v1/chat/agent`):**
```powershell
# Create chat session
$session = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/sessions" -Method Post -ContentType "application/json" -Body '{"title": "Pi SDK Agent Test", "provider": "pi_agent"}'

# Invoke agent endpoint backed by Pi SDK
curl.exe -X POST "http://127.0.0.1:8000/api/v1/chat/agent" `
  -H "Content-Type: application/json" `
  -d "{`"session_id`": `"$($session.id)`", `"message`": `"How did Brian Chesky achieve early growth at Airbnb?`", `"top_k`": 2}"
```

3. **Execute Grounded Chat Turn (Direct Local Ollama):**
```powershell
# Create session
$session = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/sessions" -Method Post -ContentType "application/json" -Body '{"title": "Retention Loops Discussion"}'

# Submit question to grounded AI agent
curl.exe -X POST "http://127.0.0.1:8000/api/v1/chat" `
  -H "Content-Type: application/json" `
  -d "{`"session_id`": `"$($session.id)`", `"message`": `"How did Brian Chesky achieve early growth at Airbnb?`", `"provider`": `"ollama`", `"top_k`": 3}"
```

4. **Generate Ship 30 for 30 Grounded Essay (`POST /api/v1/essays`):**
```powershell
# Create session
$session = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/sessions" -Method Post -ContentType "application/json" -Body '{"title": "PLG Strategy Essay"}'

# Generate essay with podcast grounding and Ollama provider
curl.exe -X POST "http://127.0.0.1:8000/api/v1/essays" `
  -H "Content-Type: application/json" `
  -d "{`"topic`": `"Product-Led Growth Loops`", `"session_id`": `"$($session.id)`", `"tone`": `"educational`", `"length`": `"standard`", `"use_podcast_grounding`": true, `"provider`": `"ollama`"}"
```

5. **Generate and Download In-App Artifact (`POST /api/v1/artifacts`):**
```powershell
# Generate Markdown deliverable from session context
$art = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/artifacts" -Method Post -ContentType "application/json" -Body "{`"session_id`": `"$($session.id)`", `"artifact_type`": `"markdown`", `"title`": `"PLG Strategy Playbook`", `"instructions`": `"Structure with executive summary, tables, and execution checklists`"}"

# Download generated artifact securely
curl.exe -OJ "http://127.0.0.1:8000/api/v1/artifacts/$($art.id)/download"
```

6. **Search Transcripts:**
```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/transcripts/search" `
  -H "Content-Type: application/json" `
  -d '{"query": "scaling teams decoupling", "top_k": 3}'
```

### 8. Frontend React UI Setup & Execution (Manual)

The frontend provides an Obsidian-themed conversational workspace connected to FastAPI and PostgreSQL with real-time model switching, Pi SDK mode, and validated YouTube timestamp links.

#### A. Install Frontend Dependencies & Start Vite Server
```powershell
cd D:\OogwayLabs\LennyGrowthAssistant\frontend
npm install
npm run dev
```
The Vite development server will start on `http://127.0.0.1:5173` and automatically proxy all `/api` requests to FastAPI on `http://127.0.0.1:8000`.

#### B. Features & Controls in UI
- **Local / Cloud Model Toggle:** Choose between **Local LLM** (`qwen2.5:1.5b` default, offline 180s timeout) and **Cloud LLM** (`gemini-3.5-flash-lite`). When `GEMINI_API_KEY` is blank, Cloud mode displays an "Unconfigured" indicator.
- **Pi Coding Agent SDK Mode:** Toggle **Pi SDK Mode** to route turns through the Node.js bridge service (`POST /api/v1/chat/agent`), enforcing read-only empty tools.
- **Session Persistence:** Create, select, and delete conversations stored permanently in PostgreSQL. Conversation history and messages are preserved across browser refreshes and provider toggles.
- **Podcast Citations & YouTube Links:** View episode titles, guest names, timestamps, relevance scores, and expandable quotes. Click "Watch on YouTube" to open authentic deep links derived from validated backend metadata.
- **Ship 30 for 30 Essay Studio:** Dedicated interactive modal workspace to draft structured short-form nonfiction essays. Features 4 configurable parameters (Topic, Target Audience, Tone, Length), custom prompt instructions, Lenny podcast RAG grounding toggle, live generation preview with word count tracking and model bounding status badges, 1-click Markdown clipboard copy, and interactive source citation drawer. Generated essays are automatically saved to conversation history.
- **Claude-Style In-App Artifact Viewer:** Side-by-side inspection panel rendering publication-grade Markdown strategy documents or self-contained HTML/CSS deliverables beside the conversation. Includes Rendered Preview and Source Code tabs, defense-in-depth script-disabled sandbox (`sandbox=""`, strict omission of `allow-same-origin`, restrictive CSP `script-src 'none'`), 1-click clipboard copy, and direct `.md` / `.html` downloads. Users can generate artifacts directly from any chat turn or from the Ship 30 Essay Studio.

---

## 🐳 9. One-Command Docker Compose Deployment (Evaluator Ready)

The application includes a fully containerized, multi-service Docker Compose topology designed for reproducible, one-command evaluator assessment on Windows 8 GB RAM machines without conflicting with active development servers.

### 9.1 Architecture & Port Isolation

| Service | Container Name | Container Port | Exposed Host Port | Conflict Protection |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend UI** | `lenny-frontend` | `80` (Nginx) | `8080` | Production React SPA with reverse proxy. Leaves host port 5173 free. |
| **Backend API** | `lenny-backend` | `8000` (FastAPI) | `8001` | REST, SSE streaming, and migrations. Leaves host port 8000 free. |
| **PostgreSQL** | `lenny-postgres` | `5432` (pgvector) | *Internal Only* | Isolated database. **Not published to host**, leaving host port 5432 free. |
| **Pi SDK Bridge**| `lenny-pi-agent` | `8765` (Node.js) | *Internal Only* | Isolated SDK daemon. **Not published to host**, leaving host port 8765 free. |
| **Ollama LLM** | *Host Machine* | `11434` (Ollama) | `11434` | Reached via `host.docker.internal:11434`. Model weights remain on host. |

### 9.2 Strict Database Isolation Policy
- **Host Data Protection:** The Docker database never touches, mounts, or overwrites your Windows host PostgreSQL database. It persists in an isolated Docker named volume (`lenny_postgres_data`).
- **Automated Idempotent Migrations:** On container startup, the backend automatically runs `alembic upgrade head`. If tables already exist, it is a safe no-op.

### 9.3 Prerequisites Before Launching Containers
1. Ensure **Docker Desktop** is running on your machine.
2. Ensure **Ollama** is running on your Windows host with `qwen2.5:1.5b`:
   ```powershell
   ollama run qwen2.5:1.5b
   ```
3. **Transcript Dataset (For Fresh Clones):** If evaluating on a brand-new machine where `data/raw_transcripts/chatprd` is not yet populated:
   ```powershell
   git clone https://github.com/ChatPRD/lennys-podcast-transcripts.git data/raw_transcripts/chatprd
   ```
   *(Note: On the existing development workspace, this dataset is already downloaded and ready).*
4. *(Optional)* Set `GEMINI_API_KEY` in your root `.env` file to enable Cloud Gemini generation. If left blank, the application functions fully in Local LLM mode.

### 9.4 Launch Application (One Command)
From the project workspace root (`D:\OogwayLabs\LennyGrowthAssistant`):
```powershell
docker compose up --build -d
```
> **Note on Initial Ingestion:** Once containers are healthy, run the quick one-time ingestion command (Section 10.1) to seed the fresh Docker database volume with podcast transcripts. Subsequent container restarts preserve all indexed data automatically.

### 9.5 Verified Access URLs
- **Web Application UI:** [http://localhost:8080](http://localhost:8080)
- **FastAPI Interactive Swagger Docs:** [http://localhost:8001/api/docs](http://localhost:8001/api/docs)
- **Backend Health Diagnostics:** [http://localhost:8001/api/v1/health](http://localhost:8001/api/v1/health)

---

## 🛠️ 10. Docker Verification, Ingestion & Troubleshooting Guide

### 10.1 First-Time Transcript Ingestion Inside Docker
If testing on a fresh machine where the database volume has not yet indexed transcripts:
```powershell
# Quick evaluation run (Indexes first 10 episodes):
docker compose exec backend python ingestion/run_ingestion.py --data-dir data/raw_transcripts/chatprd/episodes --limit 10

# Full corpus ingestion (All 270+ episodes):
docker compose exec backend python ingestion/run_ingestion.py --data-dir data/raw_transcripts/chatprd/episodes --batch-size 50
```

### 10.2 Service Health & Connectivity Probes
```powershell
# 1. Verify container status:
docker compose ps

# 2. Probe backend liveness and database connection:
curl.exe http://localhost:8001/api/v1/health

# 3. Verify Docker-to-Host Ollama connectivity from inside backend:
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags').read().decode())"

# 4. Probe Pi Coding Agent SDK daemon:
docker compose exec pi-agent curl -s http://localhost:8765/health
```

### 10.3 Inspect Container Logs
```powershell
# Stream all logs
docker compose logs -f

# Inspect specific service logs
docker compose logs -f backend
docker compose logs -f pi-agent
```

### 10.4 Normal Shutdown Without Data Loss
To stop the application while preserving your PostgreSQL database volume and transcript indexes:
```powershell
docker compose down
```
> ⚠️ **CAUTION:** Never execute `docker compose down -v` unless you explicitly want to permanently wipe the Docker database volume.

---

## 🔒 Security, Privacy & Version Control Policy
- **Public Assessment Deliverables:** Core architectural documentation (`PRD.md`, `architecture.md`, `design.md`, `README.md`), application code, and sanitized agent transcripts/evaluations are tracked for GitHub repository publication.
- **Local Isolation:** The `.gitignore` file strictly excludes `.env`, secrets, virtual environments (`.venv`), raw transcript datasets (`data/raw_transcripts/*`), processed intermediate files (`data/processed/*`), and the `private-docs/` directory (internal agile trackers, daily logs, and private planning notes remain strictly local).
- **Dataset Attribution & Personal Use:** Transcripts are attributed to Lenny's Podcast and individual guests with original YouTube URLs. In accordance with source guidelines, raw copyrighted transcripts remain strictly local and will not be committed to public Git repositories.
- **Safe Artifact Sandbox:** Generated static HTML/CSS artifacts default to script-disabled sandboxing (`sandbox=""`, `script-src 'none'`) with opaque null-origin enforcement preventing parent DOM and storage access.
