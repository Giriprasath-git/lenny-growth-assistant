import React, { useState } from 'react';
import { ChatSession } from '../../types/chat';

interface SidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
  isLoadingSessions?: boolean;
  onCollapse?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  isLoadingSessions = false,
  onCollapse,
}) => {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const handleDeleteClick = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setConfirmDeleteId(sessionId);
  };

  const handleConfirmDelete = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    onDeleteSession(sessionId);
    setConfirmDeleteId(null);
  };

  const handleCancelDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmDeleteId(null);
  };

  return (
    <aside className="app-sidebar">
      {/* New Conversation Button */}
      <button
        type="button"
        className="new-chat-btn"
        onClick={onNewSession}
        title="Start a new conversation thread (persisted to PostgreSQL)"
      >
        <span className="plus-icon">+</span>
        <span>New Conversation</span>
      </button>

      {/* Header */}
      <div className="sidebar-header-row">
        <div className="sidebar-section-header">
          <span>Conversations ({sessions.length})</span>
        </div>
        {onCollapse && (
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={onCollapse}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
          >
            ◀
          </button>
        )}
      </div>

      {/* Session List */}
      <div className="session-list">
        {isLoadingSessions ? (
          <div className="session-loading-placeholder">
            <span>Loading saved sessions...</span>
          </div>
        ) : sessions.length === 0 ? (
          <div className="session-empty-placeholder">
            <span>No previous conversations found. Click "New Conversation" above to start!</span>
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = session.id === activeSessionId;
            const isConfirming = confirmDeleteId === session.id;

            return (
              <div
                key={session.id}
                className={`session-item-wrapper ${isActive ? 'active' : ''}`}
                onClick={() => onSelectSession(session.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onSelectSession(session.id);
                }}
              >
                <div className="session-item-content">
                  <span className="session-icon">💬</span>
                  <div className="session-text-col">
                    <span className="session-title" title={session.title}>
                      {session.title || 'Untitled Conversation'}
                    </span>
                    <span className="session-meta">
                      {new Date(session.created_at).toLocaleDateString([], {
                        month: 'short',
                        day: 'numeric',
                      })}
                      {session.provider && ` • ${session.provider}`}
                    </span>
                  </div>
                </div>

                {/* Delete / Confirmation action */}
                <div className="session-actions-wrapper">
                  {isConfirming ? (
                    <div className="delete-confirm-box" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        className="delete-btn-confirm"
                        onClick={(e) => handleConfirmDelete(e, session.id)}
                        title="Confirm permanent deletion from PostgreSQL"
                      >
                        Delete
                      </button>
                      <button
                        type="button"
                        className="delete-btn-cancel"
                        onClick={handleCancelDelete}
                        title="Cancel"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="session-delete-btn"
                      onClick={(e) => handleDeleteClick(e, session.id)}
                      title="Delete conversation from database"
                      aria-label={`Delete conversation ${session.title}`}
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Host Environment Info Card */}
      <div className="sidebar-footer-card">
        <div className="footer-card-title">Host Architecture</div>
        <div className="footer-card-row">
          <span>Target RAM:</span>
          <span className="footer-card-val">8 GB Budget (6.5 GB Cap)</span>
        </div>
        <div className="footer-card-row">
          <span>Persistence:</span>
          <span className="footer-card-val">PostgreSQL + pgvector</span>
        </div>
        <div className="footer-card-row">
          <span>Local Engine:</span>
          <span className="footer-card-val">Ollama qwen2.5:1.5b</span>
        </div>
        <div className="footer-card-row">
          <span>Agent SDK:</span>
          <span className="footer-card-val">Pi Coding Agent 1.1.0</span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
