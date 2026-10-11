import React, { useState } from 'react';
import { Citation, ProviderType } from '../../types/chat';
import { EssayGenerateRequest, EssayLength, EssayResponse, EssayTone } from '../../types/essay';
import { generateEssay } from '../../services/api';
import { SourceCitationPill, CitationCard } from '../chat/SourceCitation';
import { SafeMarkdownRenderer } from '../artifacts/SafeMarkdownRenderer';

interface EssayStudioProps {
  isOpen: boolean;
  onClose: () => void;
  activeSessionId: string | null;
  provider: ProviderType;
  modelName: string;
  onEssayGenerated?: (essay: EssayResponse) => void;
  onExportAsArtifact?: (essay: EssayResponse) => void;
}

const SAMPLE_TOPICS = [
  {
    label: "Elena Verna's PLG Loops",
    topic: "Elena Verna's Product-Led Growth and B2B Retention Loops",
    instructions: "Focus on fixing churn before scaling top-of-funnel acquisition.",
  },
  {
    label: "Shreyas Doshi's LNO Framework",
    topic: "Shreyas Doshi's Leverage-Neutral-Overhead (LNO) Framework for PMs",
    instructions: "Explain how allocating time across high-leverage vs overhead tasks determines PM ROI.",
  },
  {
    label: "Brian Chesky's Early Growth",
    topic: "How Brian Chesky Scaled Airbnb with Non-Scalable High-Touch Loops",
    instructions: "Emphasize design obsession, meeting users directly, and word-of-mouth compounding.",
  },
  {
    label: "Todd Jackson's PMF Signs",
    topic: "Todd Jackson's 4 Genuine Signals of Startup Product-Market Fit",
    instructions: "Highlight demand pull, organic retention curves, and avoiding false-positive PMF.",
  },
];

export const EssayStudio: React.FC<EssayStudioProps> = ({
  isOpen,
  onClose,
  activeSessionId,
  provider,
  modelName,
  onEssayGenerated,
  onExportAsArtifact,
}) => {
  // Form State
  const [topic, setTopic] = useState<string>('');
  const [targetAudience, setTargetAudience] = useState<string>('Product Managers, Founders, & Growth Operators');
  const [tone, setTone] = useState<EssayTone>('educational');
  const [desiredLength, setDesiredLength] = useState<EssayLength>('deep_dive');
  const [specificInstructions, setSpecificInstructions] = useState<string>('');
  const [groundWithPodcasts, setGroundWithPodcasts] = useState<boolean>(true);

  // Generation & Result State
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [generatedEssay, setGeneratedEssay] = useState<EssayResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);

  if (!isOpen) return null;

  const handleSelectSample = (sample: typeof SAMPLE_TOPICS[0]) => {
    setTopic(sample.topic);
    setSpecificInstructions(sample.instructions);
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim() || isGenerating) return;

    setIsGenerating(true);
    setError(null);
    setCopied(false);
    setSelectedCitation(null);

    const payload: EssayGenerateRequest = {
      topic: topic.trim(),
      target_audience: targetAudience.trim(),
      tone,
      desired_length: desiredLength,
      specific_instructions: specificInstructions.trim() || undefined,
      ground_with_podcasts: groundWithPodcasts,
      session_id: activeSessionId || undefined,
      provider,
    };

    try {
      const result = await generateEssay(payload);
      setGeneratedEssay(result);
      if (onEssayGenerated) {
        onEssayGenerated(result);
      }
    } catch (err: any) {
      console.error('Failed to generate Ship 30 essay:', err);
      setError(err.message || 'Essay generation failed. Please check backend connection.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCopyMarkdown = () => {
    if (!generatedEssay) return;
    navigator.clipboard.writeText(generatedEssay.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    });
  };

  return (
    <div className="essay-studio-overlay" role="dialog" aria-modal="true" aria-labelledby="studio-title">
      <div className="essay-studio-modal">
        {/* Studio Header */}
        <div className="essay-studio-header">
          <div className="studio-header-titles">
            <div className="studio-brand-row">
              <span className="studio-badge">✍️ Ship 30 Studio</span>
              <span className="studio-provider-badge">
                {provider === 'cloud' ? '☁️ Cloud Gemini' : '🖥️ Local Ollama'} ({modelName})
              </span>
            </div>
            <h2 id="studio-title" className="studio-title">
              Ship 30 for 30 Essay Generator
            </h2>
            <p className="studio-subtitle">
              Synthesize high-leverage atomic essays with viral headline hooks, 1-3-1 visual pacing, and grounded podcast insights.
            </p>
          </div>
          <button type="button" className="studio-close-btn" onClick={onClose} title="Close Studio" aria-label="Close">
            ✕
          </button>
        </div>

        {/* Studio Content Grid */}
        <div className="essay-studio-body">
          {/* Left / Top Form Panel */}
          <div className="essay-form-panel">
            <form onSubmit={handleGenerate} className="essay-form">
              {/* Quick Sample Topics */}
              <div className="form-group">
                <label className="form-label">Quick Sample Frameworks:</label>
                <div className="sample-topic-chips">
                  {SAMPLE_TOPICS.map((st, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className="sample-topic-chip"
                      onClick={() => handleSelectSample(st)}
                    >
                      {st.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Central Topic Input */}
              <div className="form-group">
                <label htmlFor="essay-topic" className="form-label required">
                  Central Topic or Core Idea:
                </label>
                <input
                  id="essay-topic"
                  type="text"
                  className="essay-input"
                  placeholder="e.g. Elena Verna's B2B Product-Led Growth Retention Loops"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  required
                  disabled={isGenerating}
                />
              </div>

              {/* Target Audience */}
              <div className="form-group">
                <label htmlFor="essay-audience" className="form-label">
                  Target Readership:
                </label>
                <select
                  id="essay-audience"
                  className="essay-select"
                  value={targetAudience}
                  onChange={(e) => setTargetAudience(e.target.value)}
                  disabled={isGenerating}
                >
                  <option value="Product Managers, Founders, & Growth Operators">
                    Product Managers, Founders, & Growth Operators
                  </option>
                  <option value="Early-Stage Founders (0-to-1)">Early-Stage Founders (0-to-1)</option>
                  <option value="Growth Leads & Growth Engineers">Growth Leads & Growth Engineers</option>
                  <option value="Tech Executives, VPs, & Investors">Tech Executives, VPs, & Investors</option>
                  <option value="General Software Professionals">General Software Professionals</option>
                </select>
              </div>

              {/* Tone and Length Row */}
              <div className="form-row-two-col">
                <div className="form-group">
                  <label htmlFor="essay-tone" className="form-label">Writing Tone:</label>
                  <select
                    id="essay-tone"
                    className="essay-select"
                    value={tone}
                    onChange={(e) => setTone(e.target.value as EssayTone)}
                    disabled={isGenerating}
                  >
                    <option value="educational">Educational & Tactical</option>
                    <option value="conversational">Conversational & Direct</option>
                    <option value="professional">Professional & Analytical</option>
                    <option value="storytelling">Storytelling & Narrative</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="essay-length" className="form-label">Target Depth:</label>
                  <select
                    id="essay-length"
                    className="essay-select"
                    value={desiredLength}
                    onChange={(e) => setDesiredLength(e.target.value as EssayLength)}
                    disabled={isGenerating}
                  >
                    <option value="deep_dive">Deep-Dive (~1,000-1,250 words)</option>
                    <option value="medium">Medium (~600 words)</option>
                    <option value="short">Atomic Short (~300 words)</option>
                  </select>
                </div>
              </div>

              {/* Optional Custom Instructions */}
              <div className="form-group">
                <label htmlFor="essay-instructions" className="form-label">
                  Specific Focus or Instructions (Optional):
                </label>
                <textarea
                  id="essay-instructions"
                  className="essay-textarea"
                  placeholder="e.g. Include 4 distinct pillar frameworks, emphasize counterintuitive metrics, and end with a 5-step checklist."
                  value={specificInstructions}
                  onChange={(e) => setSpecificInstructions(e.target.value)}
                  rows={2}
                  disabled={isGenerating}
                />
              </div>

              {/* Podcast Grounding Checkbox */}
              <div className="form-group-checkbox">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={groundWithPodcasts}
                    onChange={(e) => setGroundWithPodcasts(e.target.checked)}
                    disabled={isGenerating}
                  />
                  <span>🎙️ Ground with Lenny's Podcast archives (retrieves real transcript chunks)</span>
                </label>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                className="essay-submit-btn"
                disabled={!topic.trim() || isGenerating}
              >
                {isGenerating ? (
                  <>
                    <span className="btn-spinner" />
                    <span>Synthesizing Ship 30 Essay (up to 180s)...</span>
                  </>
                ) : (
                  <>
                    <span>✍️ Generate Ship 30 Essay</span>
                  </>
                )}
              </button>
            </form>

            {/* Error Banner */}
            {error && (
              <div className="essay-error-card" role="alert">
                <span className="error-icon">⚠️</span>
                <span className="error-text">{error}</span>
              </div>
            )}
          </div>

          {/* Right / Bottom Generated Output Panel */}
          <div className="essay-preview-panel">
            {generatedEssay ? (
              <div className="generated-essay-view">
                {/* Essay Meta Action Bar */}
                <div className="essay-meta-bar">
                  <div className="essay-stat-pills">
                    <span className="stat-pill words">
                      📝 {generatedEssay.actual_word_count} words
                    </span>
                    <span className="stat-pill latency">
                      ⏱️ {(generatedEssay.latency_ms / 1000).toFixed(1)}s
                    </span>
                    <span className="stat-pill model">
                      {generatedEssay.provider} ({generatedEssay.model})
                    </span>
                    {generatedEssay.podcast_grounded && (
                      <span className="stat-pill grounded">
                        🎙️ {generatedEssay.citations?.length || 0} Citations
                      </span>
                    )}
                  </div>

                  <div className="essay-actions-group">
                    <button
                      type="button"
                      className="copy-markdown-btn"
                      onClick={handleCopyMarkdown}
                      title="Copy full essay formatted in Markdown"
                    >
                      {copied ? '✓ Copied Markdown!' : '📋 Copy Markdown'}
                    </button>
                    {onExportAsArtifact && (
                      <button
                        type="button"
                        className="export-artifact-btn"
                        onClick={() => onExportAsArtifact(generatedEssay)}
                        title="Export essay as a standalone Markdown or HTML/CSS deliverable"
                      >
                        ⚡ Save as Artifact
                      </button>
                    )}
                  </div>
                </div>

                {/* Word count limit advisory note */}
                {generatedEssay.word_count_note && (
                  <div className="word-count-note-banner">
                    ℹ️ {generatedEssay.word_count_note}
                  </div>
                )}

                {/* Main Rendered Content */}
                <div className="rendered-essay-content">
                  <div className="essay-text-body">
                    <SafeMarkdownRenderer content={generatedEssay.content} />
                  </div>
                </div>

                {/* Verified Citations Drawer */}
                {generatedEssay.citations && generatedEssay.citations.length > 0 && (
                  <div className="essay-citations-footer">
                    <div className="citations-header">
                      <span>📖 Verified Sources Grounding This Essay:</span>
                    </div>
                    <div className="citations-pill-stack">
                      {generatedEssay.citations.map((cite) => (
                        <SourceCitationPill
                          key={cite.citation_index}
                          citation={cite}
                          onClick={setSelectedCitation}
                          isActive={selectedCitation?.citation_index === cite.citation_index}
                        />
                      ))}
                    </div>

                    {selectedCitation && (
                      <div className="essay-active-citation-box">
                        <CitationCard citation={selectedCitation} initiallyExpanded={false} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : isGenerating ? (
              <div className="essay-generating-state">
                <div className="generating-pulse-icon">✍️</div>
                <h3 className="generating-title">Drafting Your Ship 30 Essay</h3>
                <p className="generating-desc">
                  Retrieving relevant transcript wisdom, structuring viral headline formulas,
                  and pacing sections with 1-3-1 cadence. Local CPU inference may take up to 180 seconds.
                </p>
                <div className="generating-progress-dots">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            ) : (
              <div className="essay-empty-state">
                <div className="empty-icon">📝</div>
                <h3 className="empty-title">Ready to Write</h3>
                <p className="empty-desc">
                  Select a sample framework on the left or enter any growth challenge to generate a complete, high-density Ship 30 for 30 essay.
                </p>
                <div className="empty-features-list">
                  <div>• Benefit-driven headline hook formulas</div>
                  <div>• 1-3-1 visual pacing & modular pillars</div>
                  <div>• Grounded in 300+ Lenny Rachitsky interviews</div>
                  <div>• Exportable clean Markdown for publishing</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
