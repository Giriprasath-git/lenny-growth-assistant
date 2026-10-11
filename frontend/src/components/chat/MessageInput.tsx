import React, { useState, KeyboardEvent, useRef, useEffect } from 'react';

interface MessageInputProps {
  onSendMessage: (content: string) => void;
  disabled?: boolean;
  ship30Active: boolean;
  onToggleShip30: () => void;
  placeholder?: string;
  isPiSdkMode?: boolean;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSendMessage,
  disabled = false,
  ship30Active,
  onToggleShip30,
  placeholder = 'Ask a question about growth loops, retention, pricing, or PM frameworks...',
  isPiSdkMode = false,
}) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-focus input when enabled
  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (trimmed && !disabled) {
      onSendMessage(trimmed);
      setText('');
      // Reset height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    // Auto-grow textarea up to max 140px
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  };

  return (
    <div className="input-dock">
      <div className={`input-box-wrapper ${disabled ? 'disabled' : ''} ${isPiSdkMode ? 'sdk-glow' : ''}`}>
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          placeholder={disabled ? 'Generating response (up to 180s)...' : placeholder}
          value={text}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={2}
          aria-label="Message input"
        />

        <div className="input-actions-bar">
          <div className="input-controls-left">
            {/* Ship 30 for 30 Writing Mode Button */}
            <button
              type="button"
              className={`skill-toggle-btn ${ship30Active ? 'active' : ''}`}
              onClick={onToggleShip30}
              disabled={disabled}
              title="Toggle Ship 30 for 30 Framework (~1,250-word structured deep dive with 1-3-1 cadence)"
              aria-pressed={ship30Active}
            >
              <span className="skill-icon">✍️</span>
              <span className="skill-label">Ship 30 Mode: {ship30Active ? 'ON' : 'OFF'}</span>
            </button>

            {isPiSdkMode && (
              <span className="pi-sdk-input-indicator" title="Submitting through Pi Coding Agent SDK Bridge">
                ⚡ Pi SDK Routing
              </span>
            )}
          </div>

          <div className="input-controls-right">
            <span className="keyboard-hint" title="Press Enter to send, Shift+Enter for a new line">
              ↵ Enter to send • ⇧↵ New line
            </span>

            <button
              type="button"
              className="send-btn"
              onClick={handleSubmit}
              disabled={!text.trim() || disabled}
              title={disabled ? 'Waiting for model...' : 'Send Message'}
              aria-label="Send message"
            >
              {disabled ? (
                <span className="send-spinner" />
              ) : (
                <span className="send-arrow">➔</span>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
