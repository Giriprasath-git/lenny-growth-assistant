/**
 * Frontend unit and contract tests for workspace layout width constraints,
 * preference resets, and HTML code fence normalization.
 *
 * Uses Node's built-in test runner (node:test) and strict assertions (node:assert/strict).
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  clampSidebarWidth,
  clampInspectorWidth,
  getDefaultLayoutPreferences,
  normalizeHtmlContent,
  MIN_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_INSPECTOR_WIDTH,
  MAX_INSPECTOR_WIDTH,
} from '../../frontend/src/utils/layout.ts';

describe('Workspace Layout Clamping & Constraints', () => {
  it('clamps sidebar width within min and max boundaries', () => {
    assert.strictEqual(clampSidebarWidth(150), MIN_SIDEBAR_WIDTH);
    assert.strictEqual(clampSidebarWidth(280), 280);
    assert.strictEqual(clampSidebarWidth(600), MAX_SIDEBAR_WIDTH);
  });

  it('clamps inspector width within min and max boundaries', () => {
    assert.strictEqual(clampInspectorWidth(200), MIN_INSPECTOR_WIDTH);
    assert.strictEqual(clampInspectorWidth(440), 440);
    assert.strictEqual(clampInspectorWidth(900), MAX_INSPECTOR_WIDTH);
  });

  it('provides balanced default layout preferences', () => {
    const defaults = getDefaultLayoutPreferences();
    assert.strictEqual(defaults.sidebarWidth, 280);
    assert.strictEqual(defaults.inspectorWidth, 440);
    assert.strictEqual(defaults.isSidebarOpen, true);
    assert.strictEqual(defaults.isSidePanelOpen, true);
  });
});

describe('HTML Artifact Code Fence Normalization', () => {
  it('strips enclosing ```html fence from start and end', () => {
    const fenced = '```html\n<!DOCTYPE html><html><body><h1>Hello</h1></body></html>\n```';
    const normalized = normalizeHtmlContent(fenced);
    assert.strictEqual(normalized, '<!DOCTYPE html><html><body><h1>Hello</h1></body></html>');
  });

  it('strips uppercase ```HTML fence', () => {
    const fenced = '```HTML\n<div>Card</div>\n```';
    const normalized = normalizeHtmlContent(fenced);
    assert.strictEqual(normalized, '<div>Card</div>');
  });

  it('leaves unfenced HTML documents intact', () => {
    const unfenced = '<!DOCTYPE html><html><body><h1>Hello</h1></body></html>';
    const normalized = normalizeHtmlContent(unfenced);
    assert.strictEqual(normalized, unfenced);
  });

  it('preserves code blocks appearing inside HTML content', () => {
    const htmlWithCode = '```html\n<div><pre><code>```python\nprint(1)\n```</code></pre></div>\n```';
    const normalized = normalizeHtmlContent(htmlWithCode);
    assert.strictEqual(normalized.startsWith('<div>'), true);
    assert.strictEqual(normalized.includes('```python'), true);
    assert.strictEqual(normalized.endsWith('</div>'), true);
  });
});
