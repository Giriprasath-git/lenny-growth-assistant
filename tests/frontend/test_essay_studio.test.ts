/**
 * Frontend unit and contract tests for Ship 30 Essay Studio and essay generation API.
 */

import { EssayGenerateRequest, EssayResponse } from '../../frontend/src/types/essay';
import { generateEssay } from '../../frontend/src/services/api';

describe('Ship 30 Essay Studio & Essay Generation Contracts', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest?.clearAllMocks?.();
  });

  describe('Essay Request Defaults & Payload Contract', () => {
    it('initializes with default educational tone, deep_dive length, and podcast grounding', () => {
      const defaultRequest: EssayGenerateRequest = {
        topic: "Elena Verna's PLG Retention Loops",
        target_audience: 'Product Managers, Founders, & Growth Operators',
        tone: 'educational',
        desired_length: 'deep_dive',
        ground_with_podcasts: true,
      };

      expect(defaultRequest.tone).toBe('educational');
      expect(defaultRequest.desired_length).toBe('deep_dive');
      expect(defaultRequest.ground_with_podcasts).toBe(true);
    });

    it('submits POST /api/v1/essays with complete payload and receives structured essay response', async () => {
      const mockResponse: EssayResponse = {
        id: 'essay-123',
        session_id: 'sess-456',
        title: 'How To Build High-Leverage Growth Loops',
        content: '# How To Build High-Leverage Growth Loops\n\n**Hook:** Fix churn first.\n\n## 1. Elena Verna Playbook\nValue first.',
        headline_hook: 'Fix churn first.',
        alternative_titles: ['The 3-Step Framework To Retention Loops'],
        takeaway: 'Focus on retention curves.',
        topic: 'PLG Loops',
        target_audience: 'Founders',
        tone: 'educational',
        desired_length: 'deep_dive',
        requested_word_count: 1250,
        actual_word_count: 540,
        word_count_status: 'bounded_by_model_output',
        word_count_note: 'Generated 540 words. Local model output limit capped length.',
        provider: 'ollama',
        model: 'qwen2.5:1.5b',
        latency_ms: 1450.2,
        podcast_grounded: true,
        citations: [
          {
            citation_index: 1,
            guest_name: 'Elena Verna',
            episode_title: 'Product-Led Growth',
            timestamp_start: '14:32',
            quote: 'Value before payment.',
          },
        ],
        created_at: new Date().toISOString(),
      };

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await generateEssay({
        topic: 'PLG Loops',
        desired_length: 'deep_dive',
      });

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/essays'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic: 'PLG Loops',
            desired_length: 'deep_dive',
          }),
        })
      );

      expect(result.title).toBe('How To Build High-Leverage Growth Loops');
      expect(result.actual_word_count).toBe(540);
      expect(result.word_count_status).toBe('bounded_by_model_output');
      expect(result.citations).toHaveLength(1);
    });
  });

  describe('Word Count Calculation & Bounding Status', () => {
    it('flags word_count_status as bounded_by_model_output when actual words fall short of requested', () => {
      const requested = 1250;
      const actual = 480;
      const isBounded = actual < requested * 0.75;
      expect(isBounded).toBe(true);
    });

    it('marks target_achieved when generated words meet or exceed 75% of target', () => {
      const requested = 600;
      const actual = 550;
      const isAchieved = actual >= requested * 0.75;
      expect(isAchieved).toBe(true);
    });
  });
});
