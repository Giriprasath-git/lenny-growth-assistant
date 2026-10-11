import React, { useState, useEffect } from 'react';
import { Artifact, ArtifactGeneratePayload } from '../../types/artifact';
import { generateArtifact } from '../../services/api';

interface ArtifactCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string | null;
  messageId?: string;
  initialContent?: string;
  provider: string;
  modelName: string;
  onArtifactCreated: (artifact: Artifact) => void;
}

export const ArtifactCreateModal: React.FC<ArtifactCreateModalProps> = ({
  isOpen,
  onClose,
  sessionId,
  messageId,
  initialContent,
  provider,
  modelName,
  onArtifactCreated,
}) => {
  const [artifactType, setArtifactType] = useState<'markdown' | 'html'>('markdown');
  const [title, setTitle] = useState('');
  const [instructions, setInstructions] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Critical Requirement: Reset form fields upon opening a new artifact creation session
  // Prevents stale document titles and instructions from persisting across creations
  useEffect(() => {
    if (isOpen) {
      setTitle('');
      setInstructions('');
      setError(null);
      setArtifactType('markdown');
    }
  }, [isOpen]);

  // Escape-to-close keyboard handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isGenerating) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isGenerating, onClose]);

  if (!isOpen) return null;

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionId) {
      setError('Active conversation session required to create an artifact.');
      return;
    }

    setIsGenerating(true);
    setError(null);

    const payload: ArtifactGeneratePayload = {
      session_id: sessionId,
      message_id: messageId,
      artifact_type: artifactType,
      title: title.trim() || undefined,
      instructions: instructions.trim() || undefined,
      custom_content: initialContent?.trim() || undefined,
      context_source: initialContent ? 'custom' : messageId ? 'message' : 'session',
      provider: provider,
    };

    try {
      const artifact = await generateArtifact(payload);
      onArtifactCreated(artifact);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to generate artifact. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-card artifact-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="artifact-modal-title"
      >
        <div className="modal-header">
          <div>
            <h2 id="artifact-modal-title" className="modal-title">
              ⚡ Generate In-App Artifact
            </h2>
            <p className="modal-subtitle">
              Synthesize conversation knowledge into a standalone deliverable rendered beside the chat.
            </p>
          </div>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close modal"
            disabled={isGenerating}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleGenerate} className="artifact-form">
          {/* Format Selection Cards */}
          <div className="form-group">
            <label className="form-label">Deliverable Format</label>
            <div className="artifact-format-grid">
              <label
                className={`format-choice-card ${artifactType === 'markdown' ? 'selected' : ''}`}
              >
                <input
                  type="radio"
                  name="artifactType"
                  value="markdown"
                  checked={artifactType === 'markdown'}
                  onChange={() => setArtifactType('markdown')}
                  disabled={isGenerating}
                />
                <div className="choice-icon">📝</div>
                <div className="choice-info">
                  <div className="choice-title">Markdown Document</div>
                  <div className="choice-desc">
                    Publication-grade strategy playbook, PRD, or review matrix with tables and checklists.
                  </div>
                </div>
              </label>

              <label
                className={`format-choice-card ${artifactType === 'html' ? 'selected' : ''}`}
              >
                <input
                  type="radio"
                  name="artifactType"
                  value="html"
                  checked={artifactType === 'html'}
                  onChange={() => setArtifactType('html')}
                  disabled={isGenerating}
                />
                <div className="choice-icon">🌐</div>
                <div className="choice-info">
                  <div className="choice-title">HTML/CSS Deliverable</div>
                  <div className="choice-desc">
                    Self-contained visual cards, scorecard layout, or interactive growth framework in sandboxed preview.
                  </div>
                </div>
              </label>
            </div>
          </div>

          {/* Optional Title Input */}
          <div className="form-group">
            <label className="form-label" htmlFor="artifact-title">
              Document Title <span className="optional-tag">(Optional)</span>
            </label>
            <input
              id="artifact-title"
              type="text"
              className="text-input"
              placeholder="e.g. B2B PLG Retention Framework Playbook"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={isGenerating}
            />
          </div>

          {/* Optional Instructions */}
          <div className="form-group">
            <label className="form-label" htmlFor="artifact-instructions">
              Custom Instructions <span className="optional-tag">(Optional)</span>
            </label>
            <textarea
              id="artifact-instructions"
              className="textarea-input"
              rows={3}
              placeholder="e.g. Emphasize Elena Verna's loop model, include a comparison table of activation metrics, and add a founder checklist."
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              disabled={isGenerating}
            />
          </div>

          {/* Source Notice & Provider Badge */}
          <div className="artifact-source-notice">
            <span>
              Context: {messageId ? 'Selected response turn' : 'Active conversation history'}
            </span>
            <span className="source-provider-pill">
              {provider === 'cloud' ? '☁️ Cloud' : provider === 'pi_agent' ? '⚡ Pi SDK' : '🖥️ Local'} ({modelName})
            </span>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="form-error-banner" role="alert">
              <span>⚠️ {error}</span>
            </div>
          )}

          {/* Action Buttons */}
          <div className="modal-actions-bar">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={isGenerating}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={isGenerating}
            >
              {isGenerating ? (
                <>
                  <span className="spinner-dots-inline">
                    <span />
                    <span />
                    <span />
                  </span>
                  Synthesizing Deliverable...
                </>
              ) : (
                '✨ Generate Deliverable'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ArtifactCreateModal;
