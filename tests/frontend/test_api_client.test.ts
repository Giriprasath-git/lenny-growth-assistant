/**
 * Unit and contract tests for the Frontend API Client Service (`frontend/src/services/api.ts`).
 * Fully mocks browser fetch. Zero network calls.
 */

import {
  createSession,
  deleteSession,
  fetchSdkStatus,
  fetchSessionDetails,
  fetchSessionMessages,
  fetchSessions,
  sendAgentChatMessage,
  sendChatMessage,
} from '../../frontend/src/services/api';

describe('Frontend API Client Service', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest?.clearAllMocks?.();
  });

  describe('fetchSdkStatus', () => {
    it('queries GET /api/v1/chat/sdk-status and returns status payload', async () => {
      const mockPayload = {
        active_default_provider: 'ollama',
        ollama_configuration: { model: 'qwen2.5:1.5b', endpoint: 'http://127.0.0.1:11434' },
        cloud_configuration: { backend: 'gemini', configured: false, model: 'gemini-3.5-flash-lite' },
        coding_agent_sdks: {
          pi_coding_agent: {
            sdk_name: 'Pi Coding Agent',
            service_health: { status: 'online', healthy: true },
          },
        },
      };

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockPayload,
      } as Response);

      const status = await fetchSdkStatus();
      expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/chat/sdk-status'));
      expect(status.active_default_provider).toBe('ollama');
      expect(status.cloud_configuration.configured).toBe(false);
      expect(status.coding_agent_sdks.pi_coding_agent.service_health?.status).toBe('online');
    });
  });

  describe('sendChatMessage', () => {
    it('submits POST /api/v1/chat with payload and returns structured turn response', async () => {
      const mockResponse = {
        session_id: 'sess-123',
        user_message: { id: 'm-1', role: 'user', content: 'What is PMF?' },
        assistant_message: {
          id: 'm-2',
          role: 'assistant',
          content: 'Todd Jackson defines PMF [1].',
          provider_metadata: { model: 'qwen2.5:1.5b', provider: 'ollama', latency_ms: 320 },
        },
        citations: [{ citation_index: 1, guest_name: 'Todd Jackson', quote: 'PMF is...' }],
        provider: 'ollama',
        model: 'qwen2.5:1.5b',
        latency_ms: 320,
        grounded_chunk_count: 5,
        is_sdk: false,
      };

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await sendChatMessage({
        session_id: 'sess-123',
        message: 'What is PMF?',
        provider: 'ollama',
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/chat'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: 'sess-123',
            message: 'What is PMF?',
            provider: 'ollama',
          }),
        })
      );

      expect(result.assistant_message.content).toContain('Todd Jackson');
      expect(result.citations).toHaveLength(1);
    });

    it('extracts structured error detail from response JSON on HTTP 502/503 failure', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => ({ detail: 'Ollama service is currently unavailable.' }),
      } as Response);

      await expect(
        sendChatMessage({
          session_id: 'sess-123',
          message: 'Hello',
        })
      ).rejects.toThrow('Ollama service is currently unavailable.');
    });
  });

  describe('sendAgentChatMessage', () => {
    it('submits POST /api/v1/chat/agent when Pi SDK mode is selected', async () => {
      const mockResponse = {
        session_id: 'sess-sdk',
        user_message: { id: 'm-u', role: 'user', content: 'SDK question' },
        assistant_message: {
          id: 'm-a',
          role: 'assistant',
          content: 'Pi Agent SDK answer.',
          provider_metadata: { framework: 'pi_coding_agent', is_sdk: true },
        },
        citations: [],
        provider: 'pi_agent',
        model: 'qwen2.5:1.5b',
        latency_ms: 450,
        framework: 'pi_coding_agent',
        is_sdk: true,
      };

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await sendAgentChatMessage({
        session_id: 'sess-sdk',
        message: 'SDK question',
        provider: 'pi_agent',
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/chat/agent'),
        expect.objectContaining({ method: 'POST' })
      );
      expect(result.is_sdk).toBe(true);
      expect(result.framework).toBe('pi_coding_agent');
    });
  });

  describe('fetchSessionMessages', () => {
    it('queries GET /api/v1/sessions/:id/messages returning chronological message list', async () => {
      const mockMessages = [
        { id: 'm-1', role: 'user', content: 'First message', created_at: '2026-10-10T10:00:00Z' },
        { id: 'm-2', role: 'assistant', content: 'First response', created_at: '2026-10-10T10:00:05Z' },
      ];

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockMessages,
      } as Response);

      const msgs = await fetchSessionMessages('sess-123');
      expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/sessions/sess-123/messages'));
      expect(msgs).toHaveLength(2);
      expect(msgs[0].role).toBe('user');
      expect(msgs[1].role).toBe('assistant');
    });
  });
});
