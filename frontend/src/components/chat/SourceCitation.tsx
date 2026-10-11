import React, { useState } from 'react';
import { Citation } from '../../types/chat';
import { getValidatedYoutubeUrl } from '../../utils/citation';

interface SourceCitationPillProps {
  citation: Citation;
  onClick: (citation: Citation) => void;
  isActive?: boolean;
}

export const SourceCitationPill: React.FC<SourceCitationPillProps> = ({
  citation,
  onClick,
  isActive = false,
}) => {
  const time = citation.timestamp_start || citation.timestamp || '';
  const guest = citation.guest_name || 'Lenny\'s Guest';

  return (
    <button
      type="button"
      className={`citation-pill ${isActive ? 'active' : ''}`}
      onClick={() => onClick(citation)}
      title={`Click to inspect verified quote from ${guest} (${time})`}
    >
      <span className="pill-index">[{citation.citation_index}]</span>
      <span className="pill-guest">{guest}</span>
      {time && <span className="pill-time">({time})</span>}
    </button>
  );
};

interface CitationCardProps {
  citation: Citation;
  initiallyExpanded?: boolean;
}

export const CitationCard: React.FC<CitationCardProps> = ({
  citation,
  initiallyExpanded = false,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(initiallyExpanded);

  const text = citation.quoted_text || citation.quote || '';
  const time = citation.timestamp_start || citation.timestamp || '';
  const guest = citation.guest_name || 'Lenny\'s Guest';
  const episode = citation.episode_title || (citation.episode_id ? `Episode ${citation.episode_id}` : 'Lenny\'s Podcast');
  const youtubeUrl = getValidatedYoutubeUrl(citation);

  const isLong = text.length > 200;
  const displayText = isLong && !isExpanded ? `${text.slice(0, 190)}...` : text;

  const relevancePercent =
    typeof citation.relevance_score === 'number'
      ? Math.round(citation.relevance_score <= 1.0 ? citation.relevance_score * 100 : citation.relevance_score)
      : null;

  return (
    <div className="citation-card-box">
      {/* Top Header */}
      <div className="citation-card-header">
        <div className="citation-title-group">
          <span className="citation-index-badge">[{citation.citation_index}]</span>
          <span className="citation-guest-name">{guest}</span>
        </div>
        <div className="citation-meta-group">
          {time && <span className="citation-timestamp">⏱️ {time}</span>}
          {relevancePercent !== null && (
            <span className="citation-relevance-pill" title={`Retriever relevance score: ${relevancePercent}%`}>
              {relevancePercent}% Match
            </span>
          )}
        </div>
      </div>

      {/* Episode title */}
      <div className="citation-episode-title">
        <span className="episode-icon">🎙️</span>
        <span className="episode-name">{episode}</span>
      </div>

      {/* Quoted Transcript Excerpt */}
      <blockquote className="citation-quote-box">
        "{displayText}"
      </blockquote>

      {/* Action Footer: Expand/Collapse & YouTube Timestamp Link */}
      <div className="citation-card-footer">
        {isLong && (
          <button
            type="button"
            className="citation-toggle-expand"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? 'Show less ▴' : 'Show full excerpt ▾'}
          </button>
        )}

        {youtubeUrl ? (
          <a
            href={youtubeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="citation-youtube-link"
            title={`Open official YouTube timestamp at ${time || 'excerpt'}`}
          >
            <span>▶ Watch on YouTube</span>
            {time && <span className="yt-timestamp">({time})</span>}
            <span className="external-arrow">↗</span>
          </a>
        ) : (
          <span className="citation-no-link-badge" title="Verified transcript record (no external video link provided)">
            🎧 Archive Transcript
          </span>
        )}
      </div>
    </div>
  );
};
