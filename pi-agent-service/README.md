# Pi Coding Agent SDK Bridge Service

Isolated Node.js/TypeScript runtime bridge embedding the official **`@earendil-works/pi-coding-agent`** SDK into **The Lenny Growth Assistant** architecture.

---

## 🚀 Overview

This service integrates the Pi Coding Agent SDK to satisfy the assignment's explicit requirement for a real coding-agent SDK runtime.

- **SDK Package:** `@earendil-works/pi-coding-agent: 1.1.0` (exact published version)
- **Official Documentation:**
  - SDK: https://pi.dev/docs/latest/sdk
  - Models: https://pi.dev/docs/latest/models
- **Model Runtime:** `ModelRuntime.create({ modelsPath })` loads catalog from `models.json` and resolves model via `modelRuntime.getModel("ollama", "qwen2.5:1.5b")`
- **Model Backend:** Local **Ollama** (`qwen2.5:1.5b`) via its OpenAI-compatible endpoint at `http://127.0.0.1:11434/v1`
- **Protocol:** `openai-completions` with local dummy authentication placeholder (`apiKey: "ollama"`)
- **Execution Mode:** In-memory agent sessions (`SessionManager.inMemory()`)
- **Authoritative Persistence:** Conversations and citations remain stored strictly in PostgreSQL
- **Security:** Strict read-only mode (`tools: []`, `noTools: "all"`, `noExtensions: true`); arbitrary shell execution, filesystem modification, and extension tool loading are strictly disabled
- **Network Interface:** Loopback only (`127.0.0.1:8765`)

---

## 🛠️ Setup Instructions (Windows PowerShell)

> **Execution Notice:** Per developer protocol, dependencies and servers must be started manually by the user.

### 1. Install Dependencies
```powershell
# Navigate to the service directory
cd D:\OogwayLabs\LennyGrowthAssistant\pi-agent-service

# Install dependencies
npm install
```

### 2. Start the Service
```powershell
# Run the service via tsx
npm start
```
Output:
```
[PiAgentService] Running on http://127.0.0.1:8765
[PiAgentService] Targeting Ollama at: http://127.0.0.1:11434/v1
[PiAgentService] Security Policy: Tools DISABLED (read-only conversational reasoning)
```

### 3. Verify Health Probe
In another terminal:
```powershell
curl.exe http://127.0.0.1:8765/health
```

### 4. Stop the Service
Press `Ctrl+C` in the terminal where `npm start` is running.

---

## 🔒 Security Restrictions
1. **Loopback Only:** Binds strictly to `127.0.0.1`, inaccessible from external network interfaces.
2. **Tools & Extensions Disabled (`tools: []`, `noTools: "all"`, `noExtensions: true`):** Prevents the agent from executing shell commands (`bash`), reading local secrets, modifying workspace files, or discovering untrusted extension tools.
3. **Bounded Tokens:** Limited to 512 response tokens, tailored for CPU inference on an 8 GB RAM host.
4. **Ephemerality:** In-memory session manager prevents leaking conversation logs to untracked disk files; PostgreSQL is the authoritative store.
