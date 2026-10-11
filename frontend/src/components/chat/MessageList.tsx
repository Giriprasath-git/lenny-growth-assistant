import React, { useEffect, useRef, useState } from 'react';
import { ChatMessage, Citation } from '../../types/chat';
import { SourceCitationPill, CitationCard } from './SourceCitation';
import { SafeMarkdownRenderer } from '../artifacts/SafeMarkdownRenderer';

interface MessageListProps {
  messages: ChatMessage[];
  onSelectCitation: (c: Citation) => void;
  activeCitation?: Citation | null;
  isLoading?: boolean;
  loadingStatusText?: string;
  onSelectSampleQuestion?: (question: string) => void;
  error?: string | null;
  onRetry?: () => void;
  onCreateArtifact?: (msg: ChatMessage) => void;
}

const SAMPLE_QUESTIONS = [
  {
    icon: '🚀',
    guest: 'Brian Chesky',
    title: 'High-Touch Growth',
    question: 'How did Brian Chesky scale Airbnb early on through non-scalable high-touch loops?',
  },
  {
    icon: '🔄',
    guest: 'Elena Verna',
    title: 'Product-Led Growth',
    question: "What is Elena Verna's framework for building a B2B product-led growth retention loop?",
  },
  {
    icon: '⏱️',
    guest: 'Shreyas Doshi',
    title: 'LNO Framework',
    question: "How does Shreyas Doshi use the Leverage-Neutral-Overhead (LNO) framework for PM prioritization?",
  },
  {
    icon: '📊',
    guest: 'Todd Jackson',
    title: 'Product-Market Fit',
    question: 'What are Todd Jackson\'s signals that an early-stage startup has genuine Product-Market Fit?',
  },
];

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  onSelectCitation,
  activeCitation,
  isLoading = false,
  loadingStatusText = 'Consulting podcast transcripts and generating response...',
  onSelectSampleQuestion,
  error = null,
  onRetry,
  onCreateArtifact,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading, error]);

  const handleCopyMarkdown = async (msg: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedMsgId(msg.id);
      setTimeout(() => setCopiedMsgId(null), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = msg.content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopiedMsgId(msg.id);
      setTimeout(() => setCopiedMsgId(null), 2000);
    }
  };

  const getModelBadge = (msg: ChatMessage) => {
    if (msg.role !== 'assistant') return null;
    const meta = msg.provider_metadata || {};
    const model = meta.model || 'qwen2.5:1.5b';
    const provider = meta.provider || 'ollama';
    const isSdk = meta.is_sdk || meta.framework === 'pi_coding_agent';

    if (isSdk) {
      return (
        <span className="model-badge sdk" title="Generated via Pi Coding Agent SDK Bridge">
          ⚡ Pi SDK ({model})
        </span>
      );
    }
    if (provider === 'cloud' || provider === 'gemini') {
      return (
        <span className="model-badge cloud" title="Generated via Cloud Gemini">
          ☁️ Cloud ({model})
        </span>
      );
    }
    return (
      <span className="model-badge local" title="Generated via Local Ollama">
        🖥️ Local ({model})
      </span>
    );
  };

  const getLatencyBadge = (msg: ChatMessage) => {
    if (msg.role !== 'assistant') return null;
    const meta = msg.provider_metadata || {};
    const latency = meta.latency_ms;
    if (typeof latency === 'number' && latency > 0) {
      const sec = (latency / 1000).toFixed(1);
      return (
        <span className="latency-badge" title={`Inference latency: ${latency}ms`}>
          ⏱️ {sec}s
        </span>
      );
    }
    return null;
  };

  return (
    <div className="message-stream">
      {messages.length === 0 ? (
        <div className="empty-state-container">
          <div className="empty-state-badge">🎙️</div>
          <h2 className="empty-state-title">
            The Lenny Growth Assistant
          </h2>
          <p className="empty-state-subtitle">
            Grounded intelligence from 300+ transcripts of Lenny's Podcast.
            Explore growth loops, retention, pricing, PM frameworks, and founder playbooks with verified citations.
          </p>

          <div className="sample-questions-grid">
            {SAMPLE_QUESTIONS.map((sq, idx) => (
              <button
                key={idx}
                type="button"
                className="sample-question-card"
                onClick={() => onSelectSampleQuestion && onSelectSampleQuestion(sq.question)}
              >
                <div className="sample-card-header">
                  <span className="sample-card-icon">{sq.icon}</span>
                  <span className="sample-card-guest">{sq.guest}</span>
                  <span className="sample-card-topic">{sq.title}</span>
                </div>
                <div className="sample-card-text">
                  "{sq.question}"
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        messages.map((msg) => (
          <div key={msg.id} className={`message-card ${msg.role}`}>
            <div className="message-header">
              <div className="message-sender">
                <span>{msg.role === 'user' ? '👤 You' : '🎙️ Lenny Assistant'}</span>
                {getModelBadge(msg)}
                {getLatencyBadge(msg)}
              </div>
              <span className="message-timestamp">
                {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>

            <div className="message-body">
              {msg.role === 'user' ? (
                <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
              ) : (
                <SafeMarkdownRenderer content={msg.content} />
              )}
            </div>

            {/* Citations Row */}
            {msg.citations && msg.citations.length > 0 && (
              <div className="message-citations-section">
                <div className="citations-header-label">
                  <span>📖 Verified Sources ({msg.citations.length}):</span>
                </div>
                <div className="citations-pills-row">
                  {msg.citations.map((cite) => (
                    <SourceCitationPill
                      key={cite.citation_index}
                      citation={cite}
                      onClick={onSelectCitation}
                      isActive={activeCitation?.citation_index === cite.citation_index}
                    />
                  ))}
                </div>

                {/* Inline preview if active citation belongs to this message */}
                {activeCitation &&
                  msg.citations.some((c) => c.citation_index === activeCitation.citation_index) && (
                    <div className="active-citation-inline-drawer">
                      <CitationCard citation={activeCitation} initiallyExpanded={false} />
                    </div>
                  )}
              </div>
            )}

            {/* Assistant Actions Bar */}
            {msg.role === 'assistant' && (
              <div className="message-actions-bar">
                <button
                  type="button"
                  className="msg-action-btn"
                  onClick={() => handleCopyMarkdown(msg)}
                  title="Copy full response formatted in Markdown"
                >
                  {copiedMsgId === msg.id ? '✓ Copied Markdown!' : '📋 Copy Markdown'}
                </button>
                {onCreateArtifact && (
                  <button
                    type="button"
                    className="msg-action-btn"
                    onClick={() => onCreateArtifact(msg)}
                    title="Create standalone deliverable (Markdown or HTML/CSS) from this answer"
                  >
                    ⚡ Create Artifact
                  </button>
                )}
              </div>
            )}
          </div>
        ))
      )}

      {/* Loading state indicator */}
      {isLoading && (
        <div className="message-card assistant loading-bubble anim-pulse">
          <div className="loading-spinner-row">
            <div className="spinner-dots">
              <span />
              <span />
              <span />
            </div>
            <div className="loading-text-col">
              <span className="loading-primary-text">{loadingStatusText}</span>
              <span className="loading-sub-text">
                Local model CPU inference may take up to 180 seconds. Please keep this tab open.
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Error state card with retry */}
      {error && (
        <div className="chat-error-banner" role="alert">
          <div className="error-icon-col">⚠️</div>
          <div className="error-content-col">
            <div className="error-title">Generation Error</div>
            <div className="error-description">{error}</div>
          </div>
          {onRetry && (
            <button type="button" className="error-retry-btn" onClick={onRetry}>
              🔄 Retry
            </button>
          )}
        </div>
      )}

      <div ref={bottomRef} style={{ height: '8px' }} />
    </div>
  );
};

export default MessageList;
