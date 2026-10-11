/**
 * Unit and contract tests for Citation processing and YouTube timestamp deep linking.
 */

import { Citation } from '../../frontend/src/types/chat';
import {
  getValidatedYoutubeUrl,
  isValidYoutubeVideoId,
  parseTimestampToSeconds,
} from '../../frontend/src/utils/citation';

describe('Citation Utilities & YouTube URL Validation', () => {
  describe('isValidYoutubeVideoId', () => {
    it('accepts authentic 11-character alphanumeric YouTube IDs', () => {
      expect(isValidYoutubeVideoId('dQw4w9WgXcQ')).toBe(true);
      expect(isValidYoutubeVideoId('4ef0juAMqoE')).toBe(true);
      expect(isValidYoutubeVideoId('kXYiU_JCYtU')).toBe(true);
      expect(isValidYoutubeVideoId('a1b2c3d4e5f')).toBe(true);
    });

    it('rejects short, long, or non-YouTube strings to avoid fabricated URLs', () => {
      expect(isValidYoutubeVideoId('too_short')).toBe(false);
      expect(isValidYoutubeVideoId('way_too_long_for_youtube_id')).toBe(false);
      expect(isValidYoutubeVideoId('')).toBe(false);
      expect(isValidYoutubeVideoId(null)).toBe(false);
      expect(isValidYoutubeVideoId(undefined)).toBe(false);
    });
  });

  describe('parseTimestampToSeconds', () => {
    it('correctly converts MM:SS into total seconds', () => {
      expect(parseTimestampToSeconds('14:32')).toBe(872);
      expect(parseTimestampToSeconds('00:45')).toBe(45);
      expect(parseTimestampToSeconds('01:00')).toBe(60);
    });

    it('correctly converts HH:MM:SS into total seconds', () => {
      expect(parseTimestampToSeconds('01:14:32')).toBe(4472);
      expect(parseTimestampToSeconds('02:00:00')).toBe(7200);
    });

    it('parses raw integer second strings', () => {
      expect(parseTimestampToSeconds('75')).toBe(75);
      expect(parseTimestampToSeconds('3600')).toBe(3600);
    });

    it('returns null on invalid or empty formats', () => {
      expect(parseTimestampToSeconds('')).toBe(null);
      expect(parseTimestampToSeconds('invalid_time')).toBe(null);
      expect(parseTimestampToSeconds(null)).toBe(null);
    });
  });

  describe('getValidatedYoutubeUrl', () => {
    it('constructs a deep link with seconds when episode_id is a valid YouTube video ID', () => {
      const citation: Citation = {
        citation_index: 1,
        episode_id: 'dQw4w9WgXcQ',
        guest_name: 'Todd Jackson',
        episode_title: 'Product-Market Fit Evaluation',
        timestamp_start: '14:32',
        quoted_text: 'Todd Jackson explains the PMF framework.',
      };

      const url = getValidatedYoutubeUrl(citation);
      expect(url).toBe('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=872s');
    });

    it('preserves verified backend youtube_timestamp_url if present', () => {
      const citation: Citation = {
        citation_index: 2,
        episode_id: 'custom-episode',
        youtube_timestamp_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120s',
        quoted_text: 'Direct quote excerpt.',
      };

      const url = getValidatedYoutubeUrl(citation);
      expect(url).toBe('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120s');
    });

    it('extracts video ID and timestamp from episode_url', () => {
      const citation: Citation = {
        citation_index: 3,
        episode_url: 'https://www.youtube.com/watch?v=4ef0juAMqoE',
        timestamp: '05:10',
        quoted_text: 'Growth loop mechanisms.',
      };

      const url = getValidatedYoutubeUrl(citation);
      expect(url).toBe('https://www.youtube.com/watch?v=4ef0juAMqoE&t=310s');
    });

    it('returns null when no authentic video ID or URL exists, preventing fabricated links', () => {
      const citation: Citation = {
        citation_index: 4,
        episode_id: 'shreyas-doshi-lno-framework', // Descriptive slug, not a YouTube ID
        guest_name: 'Shreyas Doshi',
        timestamp_start: '22:15',
        quoted_text: 'The LNO framework organizes PM tasks.',
      };

      const url = getValidatedYoutubeUrl(citation);
      expect(url).toBeNull();
    });
  });
});
