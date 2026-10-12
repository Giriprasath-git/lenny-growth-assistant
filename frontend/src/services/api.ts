/**
 * Frontend API client service.
 * Manages HTTP communication with FastAPI /api/v1 endpoints for sessions, persistence, and health probes.
 */

import {
  ChatMessage,
  ChatSession,
  ChatTurnRequest,
  ChatTurnResponse,
  SdkStatusResponse,
  SessionListResponse,
  SessionWithMessagesResponse,
  SystemHealth,
  SystemReadiness,
} from '../types/chat';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

async function parseError(response: Response, defaultMsg: string): Promise<Error> {
  try {
    const data = await response.json();
    const detail = data.detail || data.message || defaultMsg;
    return new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  } catch {
    return new Error(`${defaultMsg} (HTTP ${response.status})`);
  }
}

// ------------------------------------------------------------------------------
// Health & Diagnostics
// ------------------------------------------------------------------------------
export async function fetchHealth(): Promise<SystemHealth> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw await parseError(response, 'Health check failed');
  }
  return response.json();
}

export async function fetchLiveness(): Promise<{ status: string; timestamp: string }> {
  const response = await fetch(`${API_BASE_URL}/health/live`);
  if (!response.ok) {
    throw await parseError(response, 'Liveness check failed');
  }
  return response.json();
}

export async function fetchReadiness(): Promise<SystemReadiness> {
  const response = await fetch(`${API_BASE_URL}/health/ready`);
  if (!response.ok) {
    throw await parseError(response, 'Readiness check failed');
  }
  return response.json();
}

// ------------------------------------------------------------------------------
// SDK Status & Model Readiness
// ------------------------------------------------------------------------------
export async function fetchSdkStatus(): Promise<SdkStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/sdk-status`);
  if (!response.ok) {
    throw await parseError(response, 'Failed to fetch SDK and provider status');
  }
  return response.json();
}

// ------------------------------------------------------------------------------
// Chat & Agent Execution
// ------------------------------------------------------------------------------
export async function sendChatMessage(payload: ChatTurnRequest): Promise<ChatTurnResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, 'Chat turn execution failed');
  }
  return response.json();
}

export async function sendAgentChatMessage(payload: ChatTurnRequest): Promise<ChatTurnResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, 'Pi Coding Agent execution failed');
  }
  return response.json();
}

// ------------------------------------------------------------------------------
// Session Management & Persistence
// ------------------------------------------------------------------------------
export async function fetchSessions(limit: number = 50, offset: number = 0): Promise<SessionListResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions?limit=${limit}&offset=${offset}`);
  if (!response.ok) {
    throw await parseError(response, 'Failed to fetch sessions');
  }
  return response.json();
}

export async function fetchSessionDetails(sessionId: string): Promise<SessionWithMessagesResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`);
  if (!response.ok) {
    throw await parseError(response, `Failed to retrieve session ${sessionId}`);
  }
  return response.json();
}

export async function fetchSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/messages`);
  if (!response.ok) {
    throw await parseError(response, `Failed to retrieve messages for session ${sessionId}`);
  }
  return response.json();
}

export async function createSession(payload: {
  title?: string;
  provider?: string;
  model_name?: string;
  active_skill?: string | null;
  user_metadata?: Record<string, any>;
}): Promise<ChatSession> {
  const response = await fetch(`${API_BASE_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, 'Failed to create session');
  }
  return response.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
    method: 'DELETE',
  });
  if (!response.ok && response.status !== 204) {
    throw await parseError(response, `Failed to delete session ${sessionId}`);
  }
}

/**
 * Persists a new title for the given session via PATCH /sessions/{id}.
 * Returns the updated ChatSession on success.
 * Callers should handle failure gracefully — a title update failure must
 * never break the chat turn flow.
 */
export async function updateSessionTitle(
  sessionId: string,
  title: string
): Promise<import('../types/chat').ChatSession> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw await parseError(response, `Failed to update title for session ${sessionId}`);
  }
  return response.json();
}

export async function createSessionMessage(
  sessionId: string,
  role: 'user' | 'assistant' | 'system',
  content: string,
  providerMetadata?: Record<string, any>
): Promise<ChatMessage> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      role,
      content,
      provider_metadata: providerMetadata || {},
    }),
  });
  if (!response.ok) {
    throw await parseError(response, `Failed to store message in session ${sessionId}`);
  }
  return response.json();
}

// ------------------------------------------------------------------------------
// Ship 30 for 30 Essay Generation
// ------------------------------------------------------------------------------
export async function generateEssay(payload: import('../types/essay').EssayGenerateRequest): Promise<import('../types/essay').EssayResponse> {
  const response = await fetch(`${API_BASE_URL}/essays`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, 'Ship 30 essay generation failed');
  }
  return response.json();
}

export async function fetchEssayById(essayId: string): Promise<import('../types/essay').EssayResponse> {
  const response = await fetch(`${API_BASE_URL}/essays/${essayId}`);
  if (!response.ok) {
    throw await parseError(response, `Failed to retrieve essay ${essayId}`);
  }
  return response.json();
}

export async function fetchRecentEssays(limit: number = 20, offset: number = 0): Promise<import('../types/essay').EssayListResponse> {
  const response = await fetch(`${API_BASE_URL}/essays?limit=${limit}&offset=${offset}`);
  if (!response.ok) {
    throw await parseError(response, 'Failed to fetch recent essays');
  }
  return response.json();
}

// ------------------------------------------------------------------------------
// Phase 7: Artifact Generation, Retrieval & Downloads
// ------------------------------------------------------------------------------

export async function generateArtifact(
  payload: import('../types/artifact').ArtifactGeneratePayload
): Promise<import('../types/artifact').Artifact> {
  const response = await fetch(`${API_BASE_URL}/artifacts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await parseError(response, 'Artifact generation failed');
  }
  return response.json();
}

export async function fetchArtifact(
  artifactId: string
): Promise<import('../types/artifact').Artifact> {
  const response = await fetch(`${API_BASE_URL}/artifacts/${artifactId}`);
  if (!response.ok) {
    throw await parseError(response, `Failed to retrieve artifact ${artifactId}`);
  }
  return response.json();
}

export async function fetchSessionArtifacts(
  sessionId: string,
  limit: number = 50,
  offset: number = 0
): Promise<import('../types/artifact').ArtifactListResponse> {
  const response = await fetch(
    `${API_BASE_URL}/artifacts?session_id=${sessionId}&limit=${limit}&offset=${offset}`
  );
  if (!response.ok) {
    throw await parseError(response, `Failed to fetch artifacts for session ${sessionId}`);
  }
  return response.json();
}

export function getArtifactDownloadUrl(artifactId: string): string {
  return `${API_BASE_URL}/artifacts/${artifactId}/download`;
}

export async function deleteArtifact(artifactId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/artifacts/${artifactId}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw await parseError(response, `Failed to delete artifact ${artifactId}`);
  }
}

