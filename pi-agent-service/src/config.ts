/**
 * Configuration for the Pi Coding Agent SDK Bridge Service.
 * Tuned for 8 GB RAM host with local Ollama on loopback.
 */

export interface ServiceConfig {
  port: number;
  host: string;
  ollamaBaseUrl: string;
  defaultModel: string;
  requestTimeoutMs: number;
  maxTokens: number;
  temperature: number;
  allowedOrigins: string[];
}

export const config: ServiceConfig = {
  port: parseInt(process.env.PI_AGENT_PORT || "8765", 10),
  host: process.env.PI_AGENT_HOST || "127.0.0.1",
  ollamaBaseUrl: process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434/v1",
  defaultModel: process.env.PI_AGENT_MODEL || "qwen2.5:1.5b",
  requestTimeoutMs: parseInt(process.env.PI_AGENT_TIMEOUT_MS || "180000", 10),
  maxTokens: parseInt(process.env.PI_AGENT_MAX_TOKENS || "512", 10),
  temperature: parseFloat(process.env.PI_AGENT_TEMPERATURE || "0.2"),
  allowedOrigins: [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8001",
    "http://localhost:8001",
    "http://backend:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
  ],
};
