/**
 * Layout and normalization utilities for the resizable three-panel workspace and artifact previews.
 */

export const DEFAULT_SIDEBAR_WIDTH = 280;
export const MIN_SIDEBAR_WIDTH = 200;
export const MAX_SIDEBAR_WIDTH = 450;

export const DEFAULT_INSPECTOR_WIDTH = 440;
export const MIN_INSPECTOR_WIDTH = 320;
export const MAX_INSPECTOR_WIDTH = 720;

export const MIN_CHAT_WIDTH = 380;
export const LAYOUT_PREFS_KEY = 'lenny_layout_prefs';

export interface LayoutPreferences {
  sidebarWidth: number;
  inspectorWidth: number;
  isSidebarOpen: boolean;
  isSidePanelOpen: boolean;
}

export function clampSidebarWidth(width: number): number {
  return Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, Math.round(width)));
}

export function clampInspectorWidth(width: number): number {
  return Math.max(MIN_INSPECTOR_WIDTH, Math.min(MAX_INSPECTOR_WIDTH, Math.round(width)));
}

export function getDefaultLayoutPreferences(): LayoutPreferences {
  return {
    sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
    inspectorWidth: DEFAULT_INSPECTOR_WIDTH,
    isSidebarOpen: true,
    isSidePanelOpen: true,
  };
}

/**
 * Normalizes HTML content by stripping a single enclosing markdown code block fence (```html, ```HTML, or ```).
 * Leaves internal code blocks inside the document untouched.
 */
export function normalizeHtmlContent(content: string): string {
  let cleaned = (content || '').trim();
  const fencePrefixMatch = cleaned.match(/^```(?:html|HTML)?\s*\r?\n?/i);
  if (fencePrefixMatch) {
    cleaned = cleaned.slice(fencePrefixMatch[0].length);
    cleaned = cleaned.replace(/\r?\n?```\s*$/, '').trim();
  }
  return cleaned;
}
