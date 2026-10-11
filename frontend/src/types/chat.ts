/**
 * Chat and messaging type definitions.
 * Synchronized with Phase 2 backend Pydantic schemas.
 */

export type ProviderType = 'ollama' | 'cloud' | 'pi_agent';

export interface Citation {
  id?: string;
  citation_index: number;
  chunk_id?: string;
  episode_id?: string;
  episode_title?: string;
  guest_name?: string;
  timestamp?: string;
  timestamp_start?: string;
  timestamp_end?: string;
  quote?: string;
  quoted_text?: string;
  episode_url?: string;
  youtube_timestamp_url?: string;
  relevance_score?: number;
}

export interface ChatMessage {
  id: string;
  session_id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  provider_metadata?: {
    provider?: string;
    model?: string;
    framework?: string;
    is_sdk?: boolean;
    latency_ms?: number;
    total_tokens?: number;
    [key: string]: any;
  };
  created_at: string;
  citations?: Citation[];
  artifact_id?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  provider: string;
  model_name: string;
  active_skill: string | null;
  user_metadata?: Record<string, any>;
  created_at: string;
  updated_at?: string;
}

export interface SessionListResponse {
  items: ChatSession[];
  total: number;
  limit: number;
  offset: number;
}

export interface SessionWithMessagesResponse extends ChatSession {
  messages: ChatMessage[];
}

export interface ChatTurnRequest {
  session_id: string;
  message: string;
  provider?: 'ollama' | 'cloud' | 'gemini' | 'anthropic' | 'pi_agent';
  model?: string;
  active_skill?: string | null;
  top_k?: number;
}

export interface ChatTurnResponse {
  session_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  citations: Citation[];
  provider: string;
  model: string;
  latency_ms: number;
  grounded_chunk_count: number;
  framework?: string;
  is_sdk: boolean;
}

export interface SdkStatusResponse {
  active_default_provider: string;
  ollama_configuration: {
    endpoint: string;
    model: string;
    timeout_seconds: number;
    max_tokens: number;
    temperature: number;
    mode: string;
  };
  cloud_configuration: {
    backend: string;
    provider: string;
    model: string;
    status: string; // 'unconfigured' | 'configured_unverified' | 'verified'
    configured: boolean;
    verified: boolean;
    free_tier_eligible: boolean;
    free_tier_note?: string;
    is_optional: boolean;
    notice?: string | null;
  };
  legacy_cloud_configuration?: {
    backend: string;
    configured: boolean;
    model: string;
    is_optional: boolean;
  };
  coding_agent_sdks: {
    claude_agent_sdk: {
      sdk_name: string;
      status: string;
      details: string;
      verified_in_runtime: boolean;
    };
    pi_coding_agent: {
      sdk_name: string;
      status: string;
      details: string;
      verified_in_runtime: boolean;
      service_health?: {
        healthy: boolean;
        status: string; // 'online' | 'stopped' | 'unconfigured' | 'verified'
        configured: boolean;
        verified: boolean;
        provider: string;
        framework: string;
        service_url: string;
        base_url?: string;
        model: string;
        message?: string;
        error?: string;
        tools_count?: number;
        tools_enabled?: string[];
      };
    };
  };
}

export interface SystemReadiness {
  status: 'ready' | 'not_ready';
  ready: boolean;
  database: 'connected' | 'unavailable';
  details?: string;
  timestamp: string;
}

export interface SystemHealth {
  status: 'healthy' | 'degraded';
  app_name: string;
  version: string;
  environment: string;
  timestamp: string;
  database: {
    connected: boolean;
    status: 'connected' | 'disconnected';
    details: string;
    pool_size?: number;
    max_overflow?: number;
  };
  providers: {
    default: string;
    agent_framework?: string;
    cloud_gemini?: {
      configured: boolean;
      model: string;
      status: string;
      free_tier_eligible: boolean;
      verified?: boolean;
    };
    cloud_anthropic?: { configured: boolean; model: string };
    local_ollama: { base_url: string; model: string; timeout_seconds?: number };
  };
  system_resources?: {
    total_mb?: number;
    available_mb?: number;
    used_mb?: number;
    percent_used?: number;
    ram_warning?: boolean;
  };
}
