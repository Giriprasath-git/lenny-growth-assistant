import React, { useState } from 'react';
import { Artifact } from '../../types/artifact';
import { SandboxedPreview } from './SandboxedPreview';
import { SafeMarkdownRenderer } from './SafeMarkdownRenderer';

interface ArtifactViewerProps {
  artifact: Artifact;
  onClose?: () => void;
  sessionArtifacts?: Artifact[];
  onSelectArtifact?: (a: Artifact) => void;
}

export const ArtifactViewer: React.FC<ArtifactViewerProps> = ({
  artifact,
  onClose,
  sessionArtifacts = [],
  onSelectArtifact,
}) => {
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview');
  const [copied, setCopied] = useState(false);
  const [showSecurityInfo, setShowSecurityInfo] = useState(false);
  const [interactiveMode, setInteractiveMode] = useState(Boolean(artifact.is_interactive));

  const isHtml = artifact.artifact_type.toLowerCase() === 'html';

  // Resolve genuine model and provider labels without displaying "stored" or fabricating incorrect models
  const isModelUnavailable =
    !artifact.model_name ||
    artifact.model_name === 'Model unavailable' ||
    artifact.model_name === 'stored' ||
    artifact.provider === 'Model unavailable';

  const modelLabel = isModelUnavailable ? 'Model unavailable' : artifact.model_name;

  const providerBadge = isModelUnavailable
    ? '⚙️'
    : artifact.provider === 'cloud' || artifact.provider === 'gemini'
    ? '☁️ Cloud'
    : artifact.provider === 'pi_agent'
    ? '⚡ Pi SDK'
    : '🖥️ Local';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(artifact.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = artifact.content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    // Direct browser download via Blob to guarantee offline reliability
    const cleanTitle = (artifact.title || 'deliverable')
      .replace(/[^a-zA-Z0-9_\- ]/g, '')
      .replace(/\s+/g, '_')
      .toLowerCase();
    const ext = isHtml ? 'html' : 'md';
    const mimeType = isHtml ? 'text/html;charset=utf-8' : 'text/markdown;charset=utf-8';

    const blob = new Blob([artifact.content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${cleanTitle}.${ext}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="artifact-viewer-container">
      {/* Top Header & Selector with Non-Overlapping Layout */}
      <div className="artifact-header-bar">
        <div className="artifact-title-col">
          <div className="artifact-title-row">
            <span className="artifact-type-badge">
              {isHtml ? '🌐 HTML/CSS' : '📝 MARKDOWN'}
            </span>
            <h3 className="artifact-title" title={artifact.title}>
              {artifact.title}
            </h3>
          </div>
          <div className="artifact-meta-subtitle">
            <span>
              {isModelUnavailable ? '⚙️ Model unavailable' : `${providerBadge} (${modelLabel})`}
            </span>
            <span>•</span>
            <span>{isHtml ? 'Sandboxed Iframe' : 'Safe Document'}</span>
            <span>•</span>
            <button
              type="button"
              className="security-info-link"
              onClick={() => setShowSecurityInfo(!showSecurityInfo)}
              aria-expanded={showSecurityInfo}
            >
              🛡️ Security Policy {showSecurityInfo ? '▲' : '▼'}
            </button>
          </div>
        </div>

        {/* Action Controls Toolbar */}
        <div className="artifact-actions-row">
          <div className="artifact-tab-pill-group" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'preview'}
              className={`artifact-tab-pill ${activeTab === 'preview' ? 'active' : ''}`}
              onClick={() => setActiveTab('preview')}
            >
              Preview
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'code'}
              className={`artifact-tab-pill ${activeTab === 'code' ? 'active' : ''}`}
              onClick={() => setActiveTab('code')}
            >
              Source
            </button>
          </div>

          {isHtml && (
            <button
              type="button"
              onClick={() => setInteractiveMode(!interactiveMode)}
              className={`interactive-toggle-btn ${interactiveMode ? 'active' : ''}`}
              title="Toggle script sandbox state (Default: scripts strictly disabled)"
              aria-pressed={interactiveMode}
            >
              {interactiveMode ? '⚡ JS Active' : '🛡️ JS Disabled'}
            </button>
          )}

          <button
            type="button"
            onClick={handleCopy}
            className="artifact-icon-btn"
            title="Copy content to clipboard"
          >
            {copied ? '✓ Copied' : '📋 Copy'}
          </button>

          <button
            type="button"
            onClick={handleDownload}
            className="artifact-icon-btn primary"
            title={`Download deliverable as .${isHtml ? 'html' : 'md'}`}
          >
            ⬇️ Download
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="artifact-close-btn"
              title="Close Artifact Viewer"
              aria-label="Close Artifact Viewer"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Security Disclosure Accordion */}
      {showSecurityInfo && (
        <div className="artifact-security-banner" role="region" aria-label="Security Policy Details">
          <div className="sec-banner-header">
            <strong>🔒 Sandbox Isolation & Content Security Policy (CSP)</strong>
          </div>
          <div className="sec-banner-grid">
            <div className="sec-box allowed">
              <span className="sec-box-title">✅ Permitted Capabilities</span>
              <ul>
                <li>Self-contained HTML5 semantics and visual styling</li>
                <li>Embedded CSS styles (Flexbox, CSS Grid, animations)</li>
                <li>Responsive layouts and modern typography</li>
                <li>Base64 and HTTPS public images</li>
              </ul>
            </div>
            <div className="sec-box blocked">
              <span className="sec-box-title">🚫 Strictly Blocked</span>
              <ul>
                <li>Zero access to parent React DOM, cookies, or storage</li>
                <li>Opaque null-origin isolation (allow-same-origin omitted)</li>
                <li>Script execution disabled by default (script-src 'none')</li>
                <li>Outbound network calls (fetch, XHR, WebSocket) blocked</li>
                <li>Top-level navigation, popups, and forms disabled</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Session Artifacts Switcher (if multiple exist) */}
      {sessionArtifacts.length > 1 && onSelectArtifact && (
        <div className="session-artifacts-bar">
          <span className="session-artifacts-label">Artifacts ({sessionArtifacts.length}):</span>
          <div className="session-artifacts-chips">
            {sessionArtifacts.map((a) => (
              <button
                key={a.id}
                type="button"
                className={`session-artifact-chip ${a.id === artifact.id ? 'active' : ''}`}
                onClick={() => onSelectArtifact(a)}
                title={a.title}
              >
                {a.artifact_type === 'html' ? '🌐' : '📝'} {a.title}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main Content Stage */}
      <div className="artifact-content-stage">
        {activeTab === 'preview' ? (
          isHtml ? (
            <SandboxedPreview
              content={artifact.content}
              title={artifact.title}
              allowScripts={interactiveMode}
            />
          ) : (
            <div className="markdown-preview-scroll-wrapper">
              <SafeMarkdownRenderer content={artifact.content} />
            </div>
          )
        ) : (
          <div className="code-viewer-wrapper">
            <div className="code-viewer-header">
              <span>{isHtml ? 'HTML / CSS Source Markup' : 'Raw Markdown Content'}</span>
              <span>{artifact.content.length.toLocaleString()} characters</span>
            </div>
            <pre className="code-pre">
              <code>{artifact.content}</code>
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};

export default ArtifactViewer;
