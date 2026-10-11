/**
 * Pi Coding Agent SDK Bridge Server.
 * Isolated HTTP daemon binding strictly to 127.0.0.1:8765.
 * Exposes documented endpoints for FastAPI AgentEngine dispatch.
 */

import express, { Request, Response } from "express";
import cors from "cors";
import { config } from "./config.js";
import { executePiAgentSession, getSdkStatus, AgentPromptOptions } from "./agent.js";

const app = express();

// Security: restrict CORS strictly to local backend origins
app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin || config.allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        callback(new Error("Blocked by CORS policy for Pi Agent Service"));
      }
    },
    methods: ["GET", "POST", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
  })
);

app.use(express.json({ limit: "2mb" }));

// Liveness & Readiness probe
app.get("/health", async (_req: Request, res: Response) => {
  try {
    const sdkStatus = await getSdkStatus();
    res.json({
      status: sdkStatus.is_installed ? "ready" : "unconfigured",
      healthy: true,
      service: "pi-coding-agent-bridge",
      sdk_installed: sdkStatus.is_installed,
      sdk_package: sdkStatus.package_name,
      ollama_endpoint: sdkStatus.ollama_endpoint,
      target_model: sdkStatus.model,
      tools_enabled: sdkStatus.tools_enabled,
      security: sdkStatus.security_policies,
      timestamp: new Date().toISOString(),
    });
  } catch (err: any) {
    res.status(500).json({
      status: "error",
      healthy: false,
      message: err.message || "Failed to inspect SDK health",
    });
  }
});

// Detailed status diagnostic
app.get("/agent/status", async (_req: Request, res: Response) => {
  const sdkStatus = await getSdkStatus();
  res.json({
    ...sdkStatus,
    memory_usage: process.memoryUsage(),
    uptime_seconds: process.uptime(),
    node_version: process.version,
    host: config.host,
    port: config.port,
  });
});

// Core Agent Turn Execution endpoint
app.post("/agent/prompt", async (req: Request, res: Response) => {
  const body: AgentPromptOptions = req.body;

  if (!body.prompt || !body.prompt.trim()) {
    res.status(400).json({
      error: true,
      message: "Missing required 'prompt' field in request body.",
    });
    return;
  }

  try {
    const result = await executePiAgentSession({
      prompt: body.prompt,
      system: body.system,
      messages: body.messages,
      model: body.model || config.defaultModel,
      maxTokens: body.maxTokens || config.maxTokens,
      temperature: body.temperature ?? config.temperature,
    });

    res.json(result);
  } catch (err: any) {
    console.error("[PiAgentService] Error during agent session execution:", err);

    const isInstalledErr = err.message && err.message.includes("not installed");
    const statusCode = isInstalledErr ? 503 : 502;

    res.status(statusCode).json({
      error: true,
      provider: "pi_agent",
      framework: "pi_coding_agent",
      message: err.message || "Pi Coding Agent SDK execution failed",
      details: String(err),
    });
  }
});

// Bind strictly to loopback interface (127.0.0.1)
const server = app.listen(config.port, config.host, () => {
  console.log(`[PiAgentService] Running on http://${config.host}:${config.port}`);
  console.log(`[PiAgentService] Targeting Ollama at: ${config.ollamaBaseUrl}`);
  console.log(`[PiAgentService] Security Policy: Tools DISABLED (read-only conversational reasoning)`);
});

// Graceful termination handling
process.on("SIGINT", () => {
  console.log("[PiAgentService] Shutting down...");
  server.close(() => process.exit(0));
});

process.on("SIGTERM", () => {
  console.log("[PiAgentService] Terminated.");
  server.close(() => process.exit(0));
});

export default app;
