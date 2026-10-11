import React, { useMemo } from 'react';

interface SandboxedPreviewProps {
  content: string;
  title: string;
  allowScripts?: boolean; // Defaults to false: script-disabled sandboxing favored for static HTML/CSS
}

export const SandboxedPreview: React.FC<SandboxedPreviewProps> = ({
  content,
  title,
  allowScripts = false,
}) => {
  // Construct safe self-contained document with strict Content Security Policy
  const sanitizedSrcDoc = useMemo(() => {
    // Restrictive CSP: script-src 'none' when allowScripts is false
    const cspPolicy = allowScripts
      ? "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: https:; form-action 'none';"
      : "default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src data: https:; form-action 'none';";

    const cspMetaTag = `<meta http-equiv="Content-Security-Policy" content="${cspPolicy}">`;

    let cleaned = (content || '').trim();

    // Critical Normalization: Remove single enclosing Markdown HTML code fence (```html, ```HTML, or ```)
    // Ensures previously stored fenced artifacts and newly generated artifacts render clean HTML dashboards
    const fencePrefixMatch = cleaned.match(/^```(?:html|HTML)?\s*\r?\n?/i);
    if (fencePrefixMatch) {
      cleaned = cleaned.slice(fencePrefixMatch[0].length);
      cleaned = cleaned.replace(/\r?\n?```\s*$/, '').trim();
    }

    // Defense-in-depth sanitization when scripts are disabled
    if (!allowScripts) {
      // Strip script tags
      cleaned = cleaned.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
      // Strip inline event handlers
      cleaned = cleaned.replace(/\s+on[a-zA-Z]+\s*=\s*(?:'[^']*'|"[^"]*"|[^\s>]+)/gi, '');
      // Strip javascript: pseudo-protocol
      cleaned = cleaned.replace(/(href|src)\s*=\s*["']\s*javascript:[^"']*["']/gi, '$1="#"');
      // Strip embedding and form tags
      cleaned = cleaned.replace(/<(?:iframe|object|embed|base|form)\b[^>]*>.*?(?:<\/(?:iframe|object|embed|base|form)>|\/>)/gis, '');
    }

    // If user/model provided a complete html document, inject CSP into head
    if (cleaned.includes('<html') || cleaned.includes('<!DOCTYPE')) {
      if (cleaned.includes('<head')) {
        return cleaned.replace(/<head[^>]*>/i, `$&${cspMetaTag}`);
      } else {
        return cleaned.replace(/<html[^>]*>/i, `$&<head>${cspMetaTag}</head>`);
      }
    }

    // Otherwise wrap snippet inside a secure standard HTML canvas (with clean theme styling)
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  ${cspMetaTag}
  <style>
    body {
      margin: 0;
      padding: 20px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #FFFFFF;
      color: #292744;
      box-sizing: border-box;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  ${cleaned}
</body>
</html>`;
  }, [content, allowScripts]);

  // Detect if previously stored HTML is visibly incomplete or truncated
  const isIncomplete = useMemo(() => {
    const raw = (content || '').trim();
    if (!raw) return true;

    // Check unclosed style block
    const hasStyleOpen = /<style\b[^>]*>/i.test(raw);
    const hasStyleClose = /<\/style>/i.test(raw);
    if (hasStyleOpen && !hasStyleClose) return true;

    // Check abrupt end in CSS declaration (e.g. "color: var")
    if (/(?:var|:)\s*$/i.test(raw) && !hasStyleClose) return true;

    // Check if full document markup is present but lacks body or closing tags
    if (/<html\b|<!DOCTYPE/i.test(raw)) {
      if (!/<body\b/i.test(raw)) return true;
      if (!/<\/body>/i.test(raw) && !/<\/html>/i.test(raw)) return true;
    }

    return false;
  }, [content]);

  return (
    <div className="artifact-sandbox-container">
      {/* Security Status Bar */}
      <div
        style={{
          padding: '6px 12px',
          background: 'var(--bg-subtle)',
          borderBottom: '1px solid var(--border-subtle)',
          fontSize: '0.72rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          color: allowScripts ? 'var(--status-warning)' : 'var(--status-success)',
          fontWeight: 600,
        }}
      >
        <span>
          {allowScripts
            ? '⚠️ Sandbox: Interactive Scripts Allowed (Null Origin / Isolated)'
            : '🛡️ Sandbox: Scripts Disabled (Static HTML/CSS Safe Mode)'}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>Origin: Opaque (No Same-Origin)</span>
      </div>

      {isIncomplete ? (
        <div className="incomplete-artifact-banner">
          <div className="incomplete-artifact-card">
            <div className="incomplete-icon">⚠️</div>
            <h4 className="incomplete-title">Incomplete HTML Deliverable</h4>
            <p className="incomplete-desc">
              This deliverable was truncated during generation and contains incomplete CSS styling without a renderable body.
            </p>
            <div className="incomplete-guidance">
              <span>💡 You can view the partial markup in the <strong>Source</strong> tab, or generate a fresh deliverable using <strong>Create Artifact</strong>.</span>
            </div>
          </div>
        </div>
      ) : (
        /* 
          CRITICAL SECURITY ATTRIBUTE:
          - For static HTML/CSS: sandbox="" (scripts strictly disabled)
          - For interactive HTML/JS: sandbox="allow-scripts"
          In ALL cases, "allow-same-origin" is strictly OMITTED.
          The iframe executes within an opaque null origin with zero access to parent DOM, cookies, or storage.
        */
        <iframe
          title={title}
          className="sandboxed-iframe"
          sandbox={allowScripts ? 'allow-scripts' : ''}
          srcDoc={sanitizedSrcDoc}
        />
      )}
    </div>
  );
};

export default SandboxedPreview;
