/**
 * Type definitions for Ship 30 for 30 Essay Generation and Retrieval.
 */

import { Citation, ProviderType } from './chat';

export type EssayTone = 'educational' | 'conversational' | 'professional' | 'storytelling';
export type EssayLength = 'short' | 'medium' | 'deep_dive';

export interface EssayGenerateRequest {
  topic: string;
  target_audience?: string;
  tone?: EssayTone;
  desired_length?: EssayLength;
  specific_instructions?: string;
  ground_with_podcasts?: boolean;
  session_id?: string;
  provider?: ProviderType | 'gemini' | 'anthropic';
  model?: string;
}

export interface EssayResponse {
  id: string;
  session_id: string;
  title: string;
  content: string;
  headline_hook?: string;
  alternative_titles?: string[];
  takeaway?: string;
  topic: string;
  target_audience: string;
  tone: string;
  desired_length: string;
  requested_word_count: number;
  actual_word_count: number;
  word_count_status: string;
  word_count_note?: string;
  provider: string;
  model: string;
  latency_ms: number;
  podcast_grounded: boolean;
  citations?: Citation[];
  created_at: string;
}

export interface EssayListResponse {
  items: EssayResponse[];
  total: number;
}
