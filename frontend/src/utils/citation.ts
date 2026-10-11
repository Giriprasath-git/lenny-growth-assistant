/**
 * Citation utilities for validating backend transcript metadata and building safe YouTube timestamp links.
 */

import { Citation } from '../types/chat';

const YOUTUBE_VIDEO_ID_REGEX = /^[a-zA-Z0-9_-]{11}$/;

/**
 * Validates whether a candidate string is an authentic 11-character YouTube video ID.
 */
export function isValidYoutubeVideoId(candidate?: string | null): boolean {
  if (!candidate || typeof candidate !== 'string') return false;
  return YOUTUBE_VIDEO_ID_REGEX.test(candidate.trim());
}

/**
 * Parses timestamp string (MM:SS, HH:MM:SS, or seconds) into integer seconds.
 */
export function parseTimestampToSeconds(ts?: string | null): number | null {
  if (!ts) return null;
  const clean = String(ts).trim();
  if (!clean) return null;

  // Direct integer seconds
  if (/^\d+$/.test(clean)) {
    return parseInt(clean, 10);
  }

  // MM:SS or HH:MM:SS
  const parts = clean.split(':').map((p) => parseInt(p, 10));
  if (parts.some(isNaN)) return null;

  if (parts.length === 2) {
    const [min, sec] = parts;
    return min * 60 + sec;
  }
  if (parts.length === 3) {
    const [hr, min, sec] = parts;
    return hr * 3600 + min * 60 + sec;
  }
  return null;
}

/**
 * Returns a validated YouTube timestamp URL derived strictly from authentic backend metadata.
 * Returns null if valid YouTube video ID or URL is absent, preventing fabricated links.
 */
export function getValidatedYoutubeUrl(citation: Citation): string | null {
  // 1. If backend already provided a valid youtube_timestamp_url
  if (citation.youtube_timestamp_url && citation.youtube_timestamp_url.startsWith('https://')) {
    try {
      const parsed = new URL(citation.youtube_timestamp_url);
      if (parsed.hostname.includes('youtube.com') || parsed.hostname.includes('youtu.be')) {
        return citation.youtube_timestamp_url;
      }
    } catch {
      // Malformed URL, fall through
    }
  }

  // 2. Derive seconds from timestamp_start or timestamp
  const rawTs = citation.timestamp_start || citation.timestamp;
  const seconds = parseTimestampToSeconds(rawTs);

  // 3. Check if episode_id is an authentic 11-character YouTube video ID
  if (citation.episode_id && isValidYoutubeVideoId(citation.episode_id)) {
    const secParam = seconds !== null && seconds >= 0 ? `&t=${seconds}s` : '';
    return `https://www.youtube.com/watch?v=${citation.episode_id}${secParam}`;
  }

  // 4. Check if episode_url contains a valid YouTube watch URL
  if (citation.episode_url && citation.episode_url.startsWith('https://')) {
    try {
      const parsed = new URL(citation.episode_url);
      if (parsed.hostname.includes('youtube.com')) {
        const videoId = parsed.searchParams.get('v');
        if (videoId && isValidYoutubeVideoId(videoId)) {
          const secParam = seconds !== null && seconds >= 0 ? `&t=${seconds}s` : '';
          return `https://www.youtube.com/watch?v=${videoId}${secParam}`;
        }
      }
    } catch {
      return null;
    }
  }

  return null;
}
