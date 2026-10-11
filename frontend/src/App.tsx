import React, { useEffect, useState, useCallback } from 'react';
import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import { ChatInterface } from './components/chat/ChatInterface';
import { ArtifactViewer } from './components/artifacts/ArtifactViewer';
import { CitationCard } from './components/chat/SourceCitation';
import { EssayStudio } from './components/essay/EssayStudio';
import { ArtifactCreateModal } from './components/artifacts/ArtifactCreateModal';
import {
  ChatMessage,
  ChatSession,
  Citation,
  ProviderType,
  SdkStatusResponse,
} from './types/chat';
import { EssayResponse } from './types/essay';
import { Artifact } from './types/artifact';
import {
  createSession,
  deleteSession,
  fetchReadiness,
  fetchSdkStatus,
  fetchSessionArtifacts,
  fetchSessionDetails,
  fetchSessions,
  sendAgentChatMessage,
  sendChatMessage,
} from './services/api';

// Layout size constants (in pixels)
const DEFAULT_SIDEBAR_WIDTH = 280;
const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 450;

const DEFAULT_INSPECTOR_WIDTH = 440;
const MIN_INSPECTOR_WIDTH = 320;
const MAX_INSPECTOR_WIDTH = 720;

const MIN_CHAT_WIDTH = 380;
const LAYOUT_PREFS_KEY = 'lenny_layout_prefs';

interface LayoutPrefs {
  sidebarWidth?: number;
  inspectorWidth?: number;
  isSidebarOpen?: boolean;
  isSidePanelOpen?: boolean;
}

const loadLayoutPrefs = (): LayoutPrefs => {
  try {
    const raw = localStorage.getItem(LAYOUT_PREFS_KEY);
    if (raw) return JSON.parse(raw);
  } catch (err) {
    console.warn('Could not read layout preferences from localStorage', err);
  }
  return {};
};

export const App: React.FC = () => {
  // Provider & Skill Settings
  const [provider, setProvider] = useState<ProviderType>('ollama'); // Local is default
  const [isPiSdkMode, setIsPiSdkMode] = useState<boolean>(false);
  const [ship30Active, setShip30Active] = useState<boolean>(false);
  const [isEssayStudioOpen, setIsEssayStudioOpen] = useState<boolean>(false);

  // System Diagnostics
  const [sdkStatus, setSdkStatus] = useState<SdkStatusResponse | null>(null);
  const [dbHealthy, setDbHealthy] = useState<boolean>(true);

  // Session & Message State
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState<boolean>(true);

  // Interaction & Streaming State
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadingStatusText, setLoadingStatusText] = useState<string>('Consulting podcast transcripts...');
  const [error, setError] = useState<string | null>(null);
  const [lastFailedPrompt, setLastFailedPrompt] = useState<string | null>(null);

  // Side Panel State
  const [activeArtifact, setActiveArtifact] = useState<Artifact | null>(null);
  const [sessionArtifacts, setSessionArtifacts] = useState<Artifact[]>([]);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const [sidePanelTab, setSidePanelTab] = useState<'artifact' | 'citations'>('citations');

  // Three-Panel Resizable Layout State
  const initialPrefs = loadLayoutPrefs();
  const [sidebarWidth, setSidebarWidth] = useState<number>(
    Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, initialPrefs.sidebarWidth || DEFAULT_SIDEBAR_WIDTH))
  );
  const [inspectorWidth, setInspectorWidth] = useState<number>(
    Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, initialPrefs.inspectorWidth || DEFAULT_INSPECTOR_WIDTH))
  );
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(
    initialPrefs.isSidebarOpen !== undefined ? initialPrefs.isSidebarOpen : true
  );
  const [isSidePanelOpen, setIsSidePanelOpen] = useState<boolean>(
    initialPrefs.isSidePanelOpen !== undefined ? initialPrefs.isSidePanelOpen : true
  );

  const [isDraggingLeft, setIsDraggingLeft] = useState<boolean>(false);
  const [isDraggingRight, setIsDraggingRight] = useState<boolean>(false);

  // Artifact Modal State
  const [isArtifactModalOpen, setIsArtifactModalOpen] = useState<boolean>(false);
  const [artifactModalMessage, setArtifactModalMessage] = useState<ChatMessage | null>(null);
  const [artifactModalInitialContent, setArtifactModalInitialContent] = useState<string | undefined>(undefined);

  // Persist layout preferences to localStorage
  useEffect(() => {
    try {
      const prefs: LayoutPrefs = {
        sidebarWidth,
        inspectorWidth,
        isSidebarOpen,
        isSidePanelOpen,
      };
      localStorage.setItem(LAYOUT_PREFS_KEY, JSON.stringify(prefs));
    } catch (err) {
      console.warn('Could not save layout preferences', err);
    }
  }, [sidebarWidth, inspectorWidth, isSidebarOpen, isSidePanelOpen]);

  // Reset Layout Action
  const handleResetLayout = () => {
    setSidebarWidth(DEFAULT_SIDEBAR_WIDTH);
    setInspectorWidth(DEFAULT_INSPECTOR_WIDTH);
    setIsSidebarOpen(true);
    setIsSidePanelOpen(true);
  };

  // ----------------------------------------------------------------------------
  // Splitter Drag Handlers (Native Pointer Events)
  // ----------------------------------------------------------------------------
  const handleLeftSplitterPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    setIsDraggingLeft(true);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const onPointerMove = (moveEvent: PointerEvent) => {
      const newWidth = Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, moveEvent.clientX));
      const totalAvail = window.innerWidth;
      const rightWidth = isSidePanelOpen ? inspectorWidth : 0;
      if (totalAvail - newWidth - rightWidth >= MIN_CHAT_WIDTH) {
        setSidebarWidth(newWidth);
      }
    };

    const onPointerUp = () => {
      setIsDraggingLeft(false);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  };

  const handleRightSplitterPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    setIsDraggingRight(true);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const onPointerMove = (moveEvent: PointerEvent) => {
      const newWidth = Math.max(
        MIN_INSPECTOR_WIDTH,
        Math.min(MAX_INSPECTOR_WIDTH, window.innerWidth - moveEvent.clientX)
      );
      const leftWidth = isSidebarOpen ? sidebarWidth : 0;
      if (window.innerWidth - leftWidth - newWidth >= MIN_CHAT_WIDTH) {
        setInspectorWidth(newWidth);
      }
    };

    const onPointerUp = () => {
      setIsDraggingRight(false);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  };

  // Keyboard navigation for splitters
  const handleLeftSplitterKeyDown = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 48 : 16;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setSidebarWidth((prev) => Math.max(MIN_SIDEBAR_WIDTH, prev - step));
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      setSidebarWidth((prev) => Math.min(MAX_SIDEBAR_WIDTH, prev + step));
    } else if (e.key === 'Home') {
      e.preventDefault();
      setSidebarWidth(MIN_SIDEBAR_WIDTH);
    } else if (e.key === 'End') {
      e.preventDefault();
      setSidebarWidth(MAX_SIDEBAR_WIDTH);
    }
  };

  const handleRightSplitterKeyDown = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 48 : 16;
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      setInspectorWidth((prev) => Math.max(MIN_INSPECTOR_WIDTH, prev - step));
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setInspectorWidth((prev) => Math.min(MAX_INSPECTOR_WIDTH, prev + step));
    } else if (e.key === 'Home') {
      e.preventDefault();
      setInspectorWidth(MIN_INSPECTOR_WIDTH);
    } else if (e.key === 'End') {
      e.preventDefault();
      setInspectorWidth(MAX_INSPECTOR_WIDTH);
    }
  };

  // ----------------------------------------------------------------------------
  // 1. Initial Load: Diagnostics, Health, & Sessions
  // ----------------------------------------------------------------------------
  useEffect(() => {
    let isMounted = true;

    async function initializeApp() {
      try {
        // Probe database readiness
        const readiness = await fetchReadiness().catch(() => ({ ready: false }));
        if (isMounted) setDbHealthy(Boolean(readiness.ready));

        // Probe SDK status and model readiness
        const status = await fetchSdkStatus().catch(() => null);
        if (isMounted && status) {
          setSdkStatus(status);
        }

        // Fetch persisted sessions from PostgreSQL
        const sessionList = await fetchSessions().catch(() => ({ items: [] }));
        if (isMounted) {
          setIsLoadingSessions(false);
          if (sessionList.items && sessionList.items.length > 0) {
            setSessions(sessionList.items);
            const firstSession = sessionList.items[0];
            setActiveSessionId(firstSession.id);
            // Load messages for the first session
            loadSessionMessages(firstSession.id);
          } else {
            // Auto-create initial session
            handleNewSession();
          }
        }
      } catch (err) {
        console.error('Initialization error:', err);
        if (isMounted) setIsLoadingSessions(false);
      }
    }

    initializeApp();

    return () => {
      isMounted = false;
    };
  }, []);

  // ----------------------------------------------------------------------------
  // 2. Load Session Messages
  // ----------------------------------------------------------------------------
  const loadSessionMessages = useCallback(async (sessionId: string) => {
    try {
      setError(null);
      const details = await fetchSessionDetails(sessionId);
      setMessages(details.messages || []);
      // If messages contain citations, select the last assistant message's first citation
      const lastAssistantWithCitations = [...(details.messages || [])]
        .reverse()
        .find((m) => m.role === 'assistant' && m.citations && m.citations.length > 0);
      if (lastAssistantWithCitations?.citations?.[0]) {
        setActiveCitation(lastAssistantWithCitations.citations[0]);
      }

      // Also load persisted artifacts for this session
      fetchSessionArtifacts(sessionId)
        .then((artList) => {
          setSessionArtifacts(artList.items || []);
          if (artList.items && artList.items.length > 0) {
            setActiveArtifact(artList.items[0]);
          }
        })
        .catch((err) => {
          console.warn(`Could not load artifacts for session ${sessionId}:`, err);
        });
    } catch (err: any) {
      console.error(`Failed to load messages for session ${sessionId}:`, err);
      setError(`Failed to retrieve message history from database: ${err.message}`);
    }
  }, []);

  // Handle Session Selection
  const handleSelectSession = (sessionId: string) => {
    if (sessionId === activeSessionId) return;
    setActiveSessionId(sessionId);
    loadSessionMessages(sessionId);
  };

  // ----------------------------------------------------------------------------
  // 3. Create & Delete Sessions
  // ----------------------------------------------------------------------------
  const handleNewSession = async () => {
    try {
      const created = await createSession({
        title: 'New Conversation',
        provider,
        active_skill: ship30Active ? 'ship30' : null,
      });
      setSessions((prev) => [created, ...prev]);
      setActiveSessionId(created.id);
      setMessages([]);
      setActiveArtifact(null);
      setActiveCitation(null);
      setError(null);
    } catch (err: any) {
      console.error('Failed to create new session:', err);
      setError(`Failed to create conversation: ${err.message}`);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      const remaining = sessions.filter((s) => s.id !== sessionId);
      setSessions(remaining);

      if (sessionId === activeSessionId) {
        if (remaining.length > 0) {
          setActiveSessionId(remaining[0].id);
          loadSessionMessages(remaining[0].id);
        } else {
          handleNewSession();
        }
      }
    } catch (err: any) {
      console.error('Failed to delete session:', err);
      setError(`Failed to delete conversation: ${err.message}`);
    }
  };

  // ----------------------------------------------------------------------------
  // 4. Send Message (Chat Turn Execution)
  // ----------------------------------------------------------------------------
  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    let targetSessionId = activeSessionId;

    // Ensure an active session exists
    if (!targetSessionId) {
      try {
        const created = await createSession({
          title: text.slice(0, 40),
          provider,
          active_skill: ship30Active ? 'ship30' : null,
        });
        setSessions([created, ...sessions]);
        setActiveSessionId(created.id);
        targetSessionId = created.id;
      } catch (err: any) {
        setError(`Failed to create session: ${err.message}`);
        return;
      }
    }

    // Optimistic user message for immediate UI feedback
    const optimisticUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUserMsg]);
    setIsLoading(true);
    setError(null);
    setLastFailedPrompt(text);

    // Set contextual loading status
    if (isPiSdkMode) {
      setLoadingStatusText('Synthesizing grounded response via Pi Coding Agent SDK Bridge...');
    } else if (provider === 'cloud') {
      setLoadingStatusText('Synthesizing grounded response via Cloud Gemini...');
    } else {
      setLoadingStatusText('Retrieving podcast evidence & running local Ollama inference (up to 180s)...');
    }

    try {
      let turnResult;

      if (isPiSdkMode) {
        // Execute turn via Pi Coding Agent SDK Bridge (POST /api/v1/chat/agent)
        turnResult = await sendAgentChatMessage({
          session_id: targetSessionId,
          message: text,
          provider: 'pi_agent',
          active_skill: ship30Active ? 'ship30' : null,
        });
      } else {
        // Execute turn via standard chat endpoint (POST /api/v1/chat)
        turnResult = await sendChatMessage({
          session_id: targetSessionId,
          message: text,
          provider,
          active_skill: ship30Active ? 'ship30' : null,
        });
      }

      // Replace optimistic message with actual persisted messages from backend
      setMessages((prev) => {
        const filtered = prev.filter((m) => m.id !== optimisticUserMsg.id);
        return [...filtered, turnResult.user_message, turnResult.assistant_message];
      });

      // Update session title if first turn of a "New Conversation"
      const currentSession = sessions.find((s) => s.id === targetSessionId);
      if (currentSession && currentSession.title === 'New Conversation') {
        const derivedTitle = text.slice(0, 42) + (text.length > 42 ? '...' : '');
        setSessions((prev) =>
          prev.map((s) => (s.id === targetSessionId ? { ...s, title: derivedTitle } : s))
        );
      }

      // Select first citation if returned
      if (turnResult.citations && turnResult.citations.length > 0) {
        setActiveCitation(turnResult.citations[0]);
        setSidePanelTab('citations');
      }

      setLastFailedPrompt(null);
    } catch (err: any) {
      console.error('Chat turn execution failed:', err);
      // Remove optimistic message on error so user can re-try cleanly
      setMessages((prev) => prev.filter((m) => m.id !== optimisticUserMsg.id));
      setError(err.message || 'Execution failed. Please check backend connection.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    if (lastFailedPrompt) {
      handleSendMessage(lastFailedPrompt);
    }
  };

  const handleSelectCitation = (citation: Citation) => {
    setActiveCitation(citation);
    setSidePanelTab('citations');
    setIsSidePanelOpen(true);
  };

  // Notice banner when Cloud is chosen but not configured
  const isCloudUnconfigured = provider === 'cloud' && !sdkStatus?.cloud_configuration?.configured;

  const handleEssayGenerated = (essay: EssayResponse) => {
    if (essay.session_id === activeSessionId) {
      loadSessionMessages(activeSessionId);
    } else {
      fetchSessions().then((res) => {
        if (res.items) setSessions(res.items);
      });
      setActiveSessionId(essay.session_id);
      loadSessionMessages(essay.session_id);
    }
    if (essay.citations && essay.citations.length > 0) {
      setActiveCitation(essay.citations[0]);
    }
  };

  const handleOpenCreateArtifact = (msg?: ChatMessage, initialContent?: string) => {
    setArtifactModalMessage(msg || null);
    setArtifactModalInitialContent(initialContent || undefined);
    setIsArtifactModalOpen(true);
  };

  const handleArtifactCreated = (artifact: Artifact) => {
    setSessionArtifacts((prev) => [artifact, ...prev.filter((a) => a.id !== artifact.id)]);
    setActiveArtifact(artifact);
    setSidePanelTab('artifact');
    setIsSidePanelOpen(true);
    if (activeSessionId) {
      loadSessionMessages(activeSessionId);
    }
  };

  const handleExportEssayAsArtifact = (essay: EssayResponse) => {
    setIsEssayStudioOpen(false);
    handleOpenCreateArtifact(undefined, essay.content);
  };

  const activeModelName =
    provider === 'cloud'
      ? sdkStatus?.cloud_configuration?.model || 'gemini-3.5-flash-lite'
      : sdkStatus?.ollama_configuration?.model || 'qwen2.5:1.5b';

  return (
    <div className={`app-container ${isDraggingLeft || isDraggingRight ? 'is-resizing' : ''}`}>
      {/* Top Application Header */}
      <Header
        provider={provider}
        onProviderChange={setProvider}
        isPiSdkMode={isPiSdkMode}
        onTogglePiSdkMode={() => setIsPiSdkMode(!isPiSdkMode)}
        ship30Active={ship30Active}
        onToggleShip30={() => {
          setShip30Active(!ship30Active);
          setIsEssayStudioOpen(true);
        }}
        sdkStatus={sdkStatus}
        dbHealthy={dbHealthy}
        isSidebarOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        isSidePanelOpen={isSidePanelOpen}
        onToggleSidePanel={() => setIsSidePanelOpen(!isSidePanelOpen)}
        onResetLayout={handleResetLayout}
      />

      {/* Cloud Unconfigured Advisory Banner */}
      {isCloudUnconfigured && (
        <div className="cloud-unconfigured-banner" role="alert">
          <span className="banner-icon">ℹ️</span>
          <span className="banner-text">
            <strong>Cloud Mode Notice:</strong> A <code>GEMINI_API_KEY</code> has not been set in the server environment. Requests to Cloud mode will return a structured configuration error. You can switch back to <strong>Local LLM (qwen2.5:1.5b)</strong> at any time.
          </span>
          <button
            type="button"
            className="banner-switch-btn"
            onClick={() => setProvider('ollama')}
          >
            Switch to Local LLM
          </button>
        </div>
      )}

      {/* Main Workspace Layout with Resizable Three-Panel Structure */}
      <div className="workspace-container">
        {/* Left Panel: Conversation Sidebar */}
        {isSidebarOpen && (
          <div
            style={{ width: `${sidebarWidth}px` }}
            className="workspace-panel panel-left"
          >
            <Sidebar
              sessions={sessions}
              activeSessionId={activeSessionId}
              onSelectSession={handleSelectSession}
              onNewSession={handleNewSession}
              onDeleteSession={handleDeleteSession}
              isLoadingSessions={isLoadingSessions}
              onCollapse={() => setIsSidebarOpen(false)}
            />
          </div>
        )}

        {/* Splitter A: Between Left Sidebar and Center Chat */}
        {isSidebarOpen && (
          <div
            className={`workspace-splitter splitter-left ${isDraggingLeft ? 'is-dragging' : ''}`}
            onPointerDown={handleLeftSplitterPointerDown}
            role="separator"
            aria-orientation="vertical"
            aria-valuenow={sidebarWidth}
            aria-valuemin={MIN_SIDEBAR_WIDTH}
            aria-valuemax={MAX_SIDEBAR_WIDTH}
            tabIndex={0}
            onKeyDown={handleLeftSplitterKeyDown}
            title="Drag to resize sidebar (or use Left/Right arrow keys)"
            aria-label="Sidebar resize handle"
          >
            <div className="splitter-handle" />
          </div>
        )}

        {/* Center Panel: Main Chat Interface */}
        <main className="workspace-panel panel-center">
          <ChatInterface
            messages={messages}
            onSendMessage={handleSendMessage}
            onSelectCitation={handleSelectCitation}
            activeCitation={activeCitation}
            isLoading={isLoading}
            loadingStatusText={loadingStatusText}
            ship30Active={ship30Active}
            onToggleShip30={() => {
              setShip30Active(!ship30Active);
              setIsEssayStudioOpen(true);
            }}
            isPiSdkMode={isPiSdkMode}
            onSelectSampleQuestion={handleSendMessage}
            error={error}
            onRetry={handleRetry}
            onCreateArtifact={(msg) => handleOpenCreateArtifact(msg)}
          />
        </main>

        {/* Splitter B: Between Center Chat and Right Inspection Panel */}
        {isSidePanelOpen && (
          <div
            className={`workspace-splitter splitter-right ${isDraggingRight ? 'is-dragging' : ''}`}
            onPointerDown={handleRightSplitterPointerDown}
            role="separator"
            aria-orientation="vertical"
            aria-valuenow={inspectorWidth}
            aria-valuemin={MIN_INSPECTOR_WIDTH}
            aria-valuemax={MAX_INSPECTOR_WIDTH}
            tabIndex={0}
            onKeyDown={handleRightSplitterKeyDown}
            title="Drag to resize inspector (or use Left/Right arrow keys)"
            aria-label="Inspector resize handle"
          >
            <div className="splitter-handle" />
          </div>
        )}

        {/* Right Panel: Inspection Side Panel (Artifacts & Citations) */}
        {isSidePanelOpen && (
          <aside
            style={{ width: `${inspectorWidth}px` }}
            className="workspace-panel panel-right"
          >
            <div className="side-panel">
              <div className="side-panel-header">
                <div className="side-panel-tabs">
                  <button
                    type="button"
                    className={`panel-tab ${sidePanelTab === 'citations' ? 'active' : ''}`}
                    onClick={() => setSidePanelTab('citations')}
                  >
                    📖 Source Citations
                  </button>
                  <button
                    type="button"
                    className={`panel-tab ${sidePanelTab === 'artifact' ? 'active' : ''}`}
                    onClick={() => setSidePanelTab('artifact')}
                  >
                    ⚡ Artifact Viewer {sessionArtifacts.length > 0 ? `(${sessionArtifacts.length})` : ''}
                  </button>
                </div>
                <button
                  type="button"
                  className="panel-close-btn"
                  onClick={() => setIsSidePanelOpen(false)}
                  title="Collapse side panel"
                  aria-label="Collapse side panel"
                >
                  ✕
                </button>
              </div>

              <div className="side-panel-content">
                {sidePanelTab === 'citations' ? (
                  activeCitation ? (
                    <div className="citations-stack">
                      <CitationCard citation={activeCitation} initiallyExpanded={true} />
                    </div>
                  ) : (
                    <div className="panel-empty-state">
                      <div className="panel-empty-icon">📖</div>
                      <div className="panel-empty-title">No Citation Selected</div>
                      <p className="panel-empty-desc">
                        Click any inline citation badge in an assistant answer to inspect verified podcast transcript quotes and YouTube timestamp links.
                      </p>
                    </div>
                  )
                ) : activeArtifact ? (
                  <ArtifactViewer
                    artifact={activeArtifact}
                    onClose={() => setIsSidePanelOpen(false)}
                    sessionArtifacts={sessionArtifacts}
                    onSelectArtifact={(a) => setActiveArtifact(a)}
                  />
                ) : (
                  <div className="panel-empty-state">
                    <div className="panel-empty-icon">⚡</div>
                    <div className="panel-empty-title">Artifact Viewer</div>
                    <p className="panel-empty-desc">
                      When the assistant generates Markdown playbooks, PRDs, or self-contained HTML/CSS deliverables, they will appear sandboxed here.
                    </p>
                    <button
                      type="button"
                      className="btn-primary"
                      style={{ marginTop: '12px', fontSize: '0.8rem', padding: '8px 16px', borderRadius: 'var(--radius-sm)' }}
                      onClick={() => handleOpenCreateArtifact()}
                    >
                      ✨ Create Artifact from Chat
                    </button>
                  </div>
                )}
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* Dedicated Ship 30 for 30 Essay Studio */}
      <EssayStudio
        isOpen={isEssayStudioOpen}
        onClose={() => setIsEssayStudioOpen(false)}
        activeSessionId={activeSessionId}
        provider={provider}
        modelName={activeModelName}
        onEssayGenerated={handleEssayGenerated}
        onExportAsArtifact={handleExportEssayAsArtifact}
      />

      {/* In-App Centered Artifact Creation Modal */}
      <ArtifactCreateModal
        isOpen={isArtifactModalOpen}
        onClose={() => setIsArtifactModalOpen(false)}
        sessionId={activeSessionId}
        messageId={artifactModalMessage?.id}
        initialContent={artifactModalInitialContent}
        provider={provider}
        modelName={activeModelName}
        onArtifactCreated={handleArtifactCreated}
      />
    </div>
  );
};

export default App;
