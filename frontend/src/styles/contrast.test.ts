/**
 * WCAG 2.2 AA locks (adversarial-review hardening, ADR-0015 addendum).
 *
 * These tests parse the shipped stylesheets, so changing a color that drops a
 * text-bearing pair below 4.5:1 — or re-inverting the toggle knob — fails CI.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// vitest runs from the frontend root; jsdom rewrites import.meta.url, so the
// stylesheets are read relative to the working directory instead.
const tokensCss = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');
const appCss = readFileSync(join(process.cwd(), 'src/styles/app.css'), 'utf8');

const WHITE = '#ffffff';
const AA_NORMAL_TEXT = 4.5;

// ---- the standard WCAG relative-luminance / contrast-ratio formula ----

function channel(hexPair: string): number {
  const srgb = parseInt(hexPair, 16) / 255;
  return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(hex: string): number {
  const value = hex.replace('#', '');
  expect(value).toMatch(/^[0-9a-fA-F]{6}$/);
  const r = channel(value.slice(0, 2));
  const g = channel(value.slice(2, 4));
  const b = channel(value.slice(4, 6));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(foreground: string, background: string): number {
  const lighter = Math.max(relativeLuminance(foreground), relativeLuminance(background));
  const darker = Math.min(relativeLuminance(foreground), relativeLuminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

// ---- tiny CSS readers (enough for our hand-rolled stylesheets) ----

function tokenValue(name: string): string {
  const match = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(tokensCss);
  expect(match, `token ${name} not found in tokens.css`).not.toBeNull();
  return (match as RegExpExecArray)[1] as string;
}

/** A declaration's value with any var(--token) resolved against tokens.css. */
function resolveColor(value: string): string {
  const varMatch = /^var\((--[\w-]+)\)$/.exec(value.trim());
  return varMatch === null ? value.trim() : tokenValue(varMatch[1] as string);
}

function declaration(selector: string, property: string): string {
  const escaped = selector.replace(/[.[\]']/g, (char) => `\\${char}`);
  const block = new RegExp(`${escaped}\\s*\\{([^}]*)\\}`).exec(appCss);
  expect(block, `selector ${selector} not found in app.css`).not.toBeNull();
  const decl = new RegExp(`${property}:\\s*([^;]+);`).exec((block as RegExpExecArray)[1] as string);
  expect(decl, `${selector} { ${property}: … } not found`).not.toBeNull();
  return ((decl as RegExpExecArray)[1] as string).trim();
}

function gradientStops(selector: string): string[] {
  const background = declaration(selector, 'background');
  const inner = /linear-gradient\(140deg,\s*(.+)\)$/.exec(background);
  expect(inner, `${selector} background is not the expected linear-gradient`).not.toBeNull();
  return ((inner as RegExpExecArray)[1] as string).split(',').map(resolveColor);
}

describe('WCAG 2.2 AA contrast locks', () => {
  it('derived token --color-action-green-strong holds >=4.6:1 with white', () => {
    expect(contrastRatio(tokenValue('--color-action-green-strong'), WHITE)).toBeGreaterThanOrEqual(
      4.6,
    );
  });

  it('primary button text/background passes AA for normal text', () => {
    const background = resolveColor(declaration('.btn', 'background'));
    expect(background).toBe(tokenValue('--color-action-green-strong'));
    expect(contrastRatio(background, WHITE)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    // The hover state carries the same white text.
    expect(
      contrastRatio(resolveColor(declaration('.btn:hover', 'background')), WHITE),
    ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it.each(['.traj.improving', '.traj.declining', '.traj.stable', '.traj.insufficient_data'])(
    'every text-bearing gradient stop of %s passes AA with white',
    (selector) => {
      const stops = gradientStops(selector);
      expect(stops.length).toBeGreaterThanOrEqual(2);
      for (const stop of stops) {
        expect(contrastRatio(stop, WHITE), `stop ${stop}`).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      }
    },
  );

  it('pill.warn text on its background passes AA', () => {
    const background = resolveColor(declaration('.pill.warn', 'background'));
    const color = resolveColor(declaration('.pill.warn', 'color'));
    expect(contrastRatio(color, background)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it('clinician disclaimer text on its background passes AA', () => {
    const background = resolveColor(declaration('.disclaimer', 'background'));
    const color = resolveColor(declaration('.disclaimer', 'color'));
    expect(contrastRatio(color, background)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it('trend-table judgment words — "better" green and "worse" red — pass AA on white', () => {
    // "better" in the 14px table uses the strong green, NOT brand green (4.04:1).
    const better = resolveColor(declaration('.data-table .up', 'color'));
    expect(better).toBe(tokenValue('--color-action-green-strong'));
    expect(contrastRatio(better, WHITE)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    // "worse" red already passes — locked so it stays that way.
    expect(
      contrastRatio(resolveColor(declaration('.down', 'color')), WHITE),
    ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it('order-expiry note text passes AA on the white card', () => {
    expect(
      contrastRatio(resolveColor(declaration('.expiry', 'color')), WHITE),
    ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });

  it('panel avatar initials pass AA on the brand-blue disc', () => {
    const background = resolveColor(declaration('.prow .ava', 'background'));
    expect(contrastRatio(background, WHITE)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
  });
});

describe('toggle switch knob convention', () => {
  it('unchecked shows the knob LEFT and checked moves it RIGHT', () => {
    // Consent-integrity: patients read knob position as on/off (ADR-0015 addendum).
    expect(declaration('.tg::after', 'left')).toBe('3px');
    expect(declaration(".tg[aria-checked='true']::after", 'left')).toBe('21px');
  });
});
