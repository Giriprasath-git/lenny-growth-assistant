import React from 'react';
import { ProviderType, SdkStatusResponse } from '../../types/chat';

interface HeaderProps {
  provider: ProviderType;
  onProviderChange: (p: ProviderType) => void;
  isPiSdkMode: boolean;
  onTogglePiSdkMode: () => void;
  ship30Active: boolean;
  onToggleShip30: () => void;
  sdkStatus?: SdkStatusResponse | null;
  dbHealthy?: boolean;
  isSidebarOpen?: boolean;
  onToggleSidebar?: () => void;
  isSidePanelOpen?: boolean;
  onToggleSidePanel?: () => void;
  onResetLayout?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  provider,
  onProviderChange,
  isPiSdkMode,
  onTogglePiSdkMode,
  ship30Active,
  onToggleShip30,
  sdkStatus,
  dbHealthy = true,
  // isSidebarOpen, onToggleSidebar, isSidePanelOpen, onToggleSidePanel, onResetLayout
  // are accepted as props for API compatibility but not rendered (layout controls removed).
}) => {
  const cloudConfig = sdkStatus?.cloud_configuration;
  const isCloudConfigured = Boolean(cloudConfig?.configured);
  const cloudModelName = cloudConfig?.model || 'gemini-3.5-flash-lite';
  const ollamaModelName = sdkStatus?.ollama_configuration?.model || 'qwen2.5:1.5b';

  const piHealth = sdkStatus?.coding_agent_sdks?.pi_coding_agent?.service_health;
  const isPiOnline = piHealth?.status === 'online' || piHealth?.status === 'verified';

  return (
    <header className="app-header">
      {/* LEFT: Brand Identity */}
      <div className="brand-section">
        <div className="brand-logo-badge" aria-hidden="true">🎙️</div>
        <div className="brand-titles">
          <h1 className="brand-title">The Lenny Growth Assistant</h1>
          <span className="brand-subtitle">Podcast Knowledge RAG</span>
        </div>
      </div>

      {/* CENTER: Local vs Cloud Provider Selector */}
      <div className="header-center-section">
        <div className="provider-toggle-pills" role="radiogroup" aria-label="Model Provider Selection">
          {/* Local Ollama Option (Default) */}
          <button
            type="button"
            className={`provider-pill ${provider === 'ollama' ? 'active' : ''}`}
            onClick={() => onProviderChange('ollama')}
            role="radio"
            aria-checked={provider === 'ollama'}
            title={`Local Ollama (${ollamaModelName}) - Offline loopback inference, 180s timeout`}
          >
            <span className="pill-icon">🖥️</span>
            <span className="pill-name">Local LLM</span>
            <span className="pill-model-name">({ollamaModelName})</span>
          </button>

          {/* Cloud Gemini Option */}
          <button
            type="button"
            className={`provider-pill ${provider === 'cloud' ? 'active' : ''} ${!isCloudConfigured ? 'unconfigured' : ''}`}
            onClick={() => onProviderChange('cloud')}
            role="radio"
            aria-checked={provider === 'cloud'}
            title={
              isCloudConfigured
                ? `Cloud Gemini (${cloudModelName}) - Free-tier text generation`
                : `Cloud Gemini (${cloudModelName}) - Unconfigured (Set GEMINI_API_KEY in backend .env)`
            }
          >
            <span className="pill-icon">☁️</span>
            <span className="pill-name">Cloud LLM</span>
            <span className="pill-model-name">({cloudModelName})</span>
            {!isCloudConfigured && (
              <span className="pill-unconfigured-badge" title="No GEMINI_API_KEY configured in backend .env">
                Unconfigured
              </span>
            )}
          </button>
        </div>
      </div>

      {/* RIGHT: Operational Mode Controls & Secondary Layout Tools */}
      <div className="header-right-section">
        {/* Pi Coding Agent SDK Mode Toggle */}
        <button
          type="button"
          className={`pi-sdk-toggle-btn ${isPiSdkMode ? 'active' : ''} ${!isPiOnline ? 'offline' : ''}`}
          onClick={onTogglePiSdkMode}
          title={
            isPiOnline
              ? 'Toggle Pi Coding Agent SDK Bridge (127.0.0.1:8765) - Strict read-only tools: []'
              : 'Pi Coding Agent Bridge daemon (127.0.0.1:8765) is offline. Start via: cd pi-agent-service && npm start'
          }
          aria-pressed={isPiSdkMode}
        >
          <span className="sdk-icon">⚡</span>
          <span className="sdk-text">Pi SDK: {isPiSdkMode ? 'ON' : 'OFF'}</span>
          <span
            className={`sdk-status-dot ${isPiOnline ? 'online' : 'offline'}`}
            title={isPiOnline ? 'Pi Bridge daemon running' : 'Pi Bridge stopped'}
          />
        </button>

        {/* Ship 30 Writing Mode Button */}
        <button
          type="button"
          className={`skill-header-toggle-btn ${ship30Active ? 'active' : ''}`}
          onClick={onToggleShip30}
          title="Toggle Ship 30 for 30 Writing Framework (~1,250-word structured deep-dive format)"
          aria-pressed={ship30Active}
        >
          <span>✍️</span>
          <span>Ship 30: {ship30Active ? 'ON' : 'OFF'}</span>
        </button>

        {/* Database & System Health Pill */}
        <div
          className={`system-health-pill ${dbHealthy ? 'healthy' : 'degraded'}`}
          title={dbHealthy ? 'PostgreSQL and FastAPI operational' : 'Database connection warning'}
        >
          <span className="health-dot" />
          <span className="health-text">{dbHealthy ? 'Ready' : 'DB Offline'}</span>
        </div>

      </div>
    </header>
  );
};

export default Header;
