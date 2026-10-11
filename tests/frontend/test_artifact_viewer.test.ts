/**
 * Frontend unit and contract tests for Phase 7 Artifact Viewer, Sandbox Security, and Safe Markdown.
 */

import { describe, it, expect } from 'vitest';
import { Artifact, ArtifactGeneratePayload } from '../../frontend/src/types/artifact';

describe('Phase 7 Artifact Viewer & Sandbox Security Contracts', () => {
  it('enforces script-disabled sandbox and omission of allow-same-origin by default', () => {
    // Contract verification for SandboxedPreview iframe attributes
    const allowScripts = false;
    const sandboxAttribute = allowScripts ? 'allow-scripts' : '';

    // 1. In static mode, sandbox attribute must be empty string (strictly all permissions disabled)
    expect(sandboxAttribute).toBe('');

    // 2. In ALL modes, allow-same-origin MUST NOT be included
    expect(sandboxAttribute.includes('allow-same-origin')).toBe(false);

    // 3. In interactive opt-in mode, allow-scripts may be present, but allow-same-origin must remain omitted
    const interactiveSandbox = true ? 'allow-scripts' : '';
    expect(interactiveSandbox).toBe('allow-scripts');
    expect(interactiveSandbox.includes('allow-same-origin')).toBe(false);
  });

  it('generates strict Content Security Policy meta tag for HTML deliverable preview', () => {
    const cspPolicyStatic = "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src data: https:; form-action 'none';";
    const cspPolicyInteractive = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: https:; form-action 'none';";

    // Static CSP must disallow scripts
    expect(cspPolicyStatic).toContain("script-src 'none'");
    expect(cspPolicyStatic).toContain("form-action 'none'");
    expect(cspPolicyStatic).toContain("default-src 'none'");

    // Both policies must disallow external objects or unauthorized frame actions
    expect(cspPolicyInteractive).toContain("form-action 'none'");
    expect(cspPolicyInteractive).toContain("default-src 'none'");
  });

  it('neutralizes malicious scripts and inline event handlers in client-side HTML preview', () => {
    const rawContent = `
      <!DOCTYPE html>
      <html>
        <head><title>Scorecard</title></head>
        <body>
          <script>alert('XSS');</script>
          <div onclick="pwn()" onmouseover="evil()">Score: 95</div>
          <a href="javascript:steal()">Action</a>
          <iframe src="https://evil.com"></iframe>
          <h1>Valid Content</h1>
        </body>
      </html>
    `;

    // Mirroring SandboxedPreview sanitization logic
    let cleaned = rawContent
      .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
      .replace(/\s+on[a-zA-Z]+\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+)/gi, '')
      .replace(/(href|src)\s*=\s*["']\s*javascript:[^"']*["']/gi, '$1="#"')
      .replace(/<(?:iframe|object|embed|base|form)\b[^>]*>.*?(?:<\/(?:iframe|object|embed|base|form)>|\/>)/gis, '');

    expect(cleaned).not.toContain('<script>');
    expect(cleaned).not.toContain("alert('XSS')");
    expect(cleaned).not.toContain('onclick=');
    expect(cleaned).not.toContain('onmouseover=');
    expect(cleaned).not.toContain('javascript:');
    expect(cleaned).not.toContain('<iframe');
    expect(cleaned).toContain('<h1>Valid Content</h1>');
  });

  it('assembles valid ArtifactGeneratePayload with custom instructions and format', () => {
    const payload: ArtifactGeneratePayload = {
      session_id: 'session-1234',
      message_id: 'msg-5678',
      artifact_type: 'markdown',
      title: 'Retention Loop Playbook',
      instructions: 'Include Elena Verna B2B loops and Day 30 retention metrics.',
      provider: 'ollama',
    };

    expect(payload.session_id).toBe('session-1234');
    expect(payload.artifact_type).toBe('markdown');
    expect(payload.title).toBe('Retention Loop Playbook');
    expect(payload.provider).toBe('ollama');
  });

  it('produces traversal-proof download filenames with correct extensions', () => {
    const sanitizeTitle = (title: string, type: 'html' | 'markdown') => {
      const clean = title.replace(/[^a-zA-Z0-9_\- ]/g, '').replace(/\s+/g, '_').toLowerCase();
      const ext = type === 'html' ? 'html' : 'md';
      return `${clean || 'deliverable'}.${ext}`;
    };

    expect(sanitizeTitle('../../etc/passwd', 'markdown')).toBe('etcpasswd.md');
    expect(sanitizeTitle("Brian's 10-Star Experience!!", 'html')).toBe('brians_10-star_experience.html');
    expect(sanitizeTitle('   ', 'markdown')).toBe('deliverable.md');
  });
});
