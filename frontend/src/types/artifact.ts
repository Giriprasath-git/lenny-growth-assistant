/**
 * Artifact and secure sandbox type definitions.
 */

export type ArtifactType = 'html' | 'markdown' | 'css' | 'json';

export interface Artifact {
  id: string;
  session_id: string;
  message_id?: string;
  artifact_type: ArtifactType;
  title: string;
  content: string;
  provider?: string;
  model_name?: string;
  is_interactive?: boolean; // Defaults to false: static HTML/CSS with script-disabled sandbox
  is_sanitized?: boolean;
  security_policy?: {
    sandbox?: string;
    allow_scripts?: boolean;
    allow_same_origin?: boolean;
    csp_enforced?: boolean;
    blocked_features?: string[];
  };
  metadata?: Record<string, any>;
  created_at: string;
}

export interface ArtifactGeneratePayload {
  session_id: string;
  message_id?: string;
  artifact_type: 'markdown' | 'html';
  title?: string;
  instructions?: string;
  context_source?: 'session' | 'message' | 'custom' | 'essay';
  custom_content?: string;
  provider?: string;
}

export interface ArtifactListResponse {
  items: Artifact[];
  total: number;
}

export interface SandboxSecurityConfig {
  allowScripts: boolean; // False by default; favored script-disabled sandboxing for static HTML/CSS
  allowSameOrigin: false; // Strictly false: guarantees opaque null-origin isolation
  cspHeader: string;
}
