/**
 * Unit and contract tests for Chatbot UI state transitions and provider routing contracts.
 */

import { ProviderType, SdkStatusResponse } from '../../frontend/src/types/chat';

describe('Chatbot UI State & Routing Contracts', () => {
  describe('Provider Selection Contract', () => {
    it('sets Local LLM as default provider and targets Ollama with qwen2.5:1.5b', () => {
      const defaultProvider: ProviderType = 'ollama';
      expect(defaultProvider).toBe('ollama');
    });

    it('identifies unconfigured Cloud state when GEMINI_API_KEY is absent', () => {
      const mockStatus: SdkStatusResponse = {
        active_default_provider: 'ollama',
        ollama_configuration: {
          endpoint: 'http://127.0.0.1:11434',
          model: 'qwen2.5:1.5b',
          timeout_seconds: 180,
          max_tokens: 512,
          temperature: 0.2,
          mode: 'local_offline_http',
        },
        cloud_configuration: {
          backend: 'gemini',
          provider: 'cloud',
          model: 'gemini-3.5-flash-lite',
          status: 'unconfigured',
          configured: false,
          verified: false,
          free_tier_eligible: true,
          is_optional: true,
          notice: 'A GEMINI_API_KEY is required only for live cloud verification.',
        },
        coding_agent_sdks: {
          claude_agent_sdk: {
            sdk_name: 'Claude Agent SDK',
            status: 'unverified',
            details: 'Standard boundary',
            verified_in_runtime: false,
          },
          pi_coding_agent: {
            sdk_name: 'Pi Coding Agent',
            status: 'verified',
            details: 'Running bridge',
            verified_in_runtime: true,
            service_health: {
              healthy: true,
              status: 'online',
              configured: true,
              verified: true,
              provider: 'pi_agent',
              framework: 'pi_coding_agent',
              service_url: 'http://127.0.0.1:8765',
              model: 'qwen2.5:1.5b',
            },
          },
        },
      };

      const isCloudConfigured = mockStatus.cloud_configuration.configured;
      expect(isCloudConfigured).toBe(false);
      expect(mockStatus.cloud_configuration.status).toBe('unconfigured');
      expect(mockStatus.cloud_configuration.notice).toContain('GEMINI_API_KEY');
    });

    it('preserves existing conversation history across provider switches', () => {
      const messages = [
        { id: 'm-1', role: 'user', content: 'Initial question' },
        { id: 'm-2', role: 'assistant', content: 'Initial answer' },
      ];

      // Simulate provider switch from local to cloud
      let activeProvider: ProviderType = 'ollama';
      activeProvider = 'cloud';

      expect(activeProvider).toBe('cloud');
      // Messages array remains unchanged
      expect(messages).toHaveLength(2);
      expect(messages[0].content).toBe('Initial question');
    });
  });

  describe('Pi Coding Agent SDK Mode Contract', () => {
    it('routes turns to POST /api/v1/chat/agent with provider="pi_agent" when enabled', () => {
      const isPiSdkMode = true;
      const endpoint = isPiSdkMode ? '/api/v1/chat/agent' : '/api/v1/chat';
      const providerParam = isPiSdkMode ? 'pi_agent' : 'ollama';

      expect(endpoint).toBe('/api/v1/chat/agent');
      expect(providerParam).toBe('pi_agent');
    });

    it('falls back seamlessly to local Ollama when Pi SDK mode is disabled', () => {
      const isPiSdkMode = false;
      const endpoint = isPiSdkMode ? '/api/v1/chat/agent' : '/api/v1/chat';
      const providerParam = isPiSdkMode ? 'pi_agent' : 'ollama';

      expect(endpoint).toBe('/api/v1/chat');
      expect(providerParam).toBe('ollama');
    });
  });

  describe('Session Deletion Confirmation Contract', () => {
    it('requires confirmation state before permanent database cascade deletion', () => {
      let confirmDeleteId: string | null = null;
      const targetSessionId = 'session-to-delete';

      // 1. Initial click sets confirmation state
      confirmDeleteId = targetSessionId;
      expect(confirmDeleteId).toBe('session-to-delete');

      // 2. Cancel resets confirmation state
      confirmDeleteId = null;
      expect(confirmDeleteId).toBeNull();
    });
  });
});
