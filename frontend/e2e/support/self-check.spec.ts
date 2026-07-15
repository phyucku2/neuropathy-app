/**
 * Self-check for the zero-console-errors gate (ADR-0022).
 *
 * A gate that never fails proves nothing. These specs prove the gate in fixtures.ts
 * works in BOTH directions, so a regression that weakened it would itself be caught:
 *   1. `isAllowed` classifies the designed, handled statuses as benign AND classifies
 *      a genuine fault (a 500 — including the mock's "Unmocked path" 500 — a pageerror,
 *      or an app-origin console.error) as NOT benign.
 *   2. A real error thrown in a real browser actually surfaces on the `pageerror` /
 *      `console` streams the gate listens to — i.e. the detection wiring observes
 *      errors, it is not a no-op.
 *
 * Uses the BASE Playwright test (not the console-gated `test` from fixtures) so these
 * checks can deliberately observe errors without the auto-gate failing them.
 */

import { test as base, expect } from '@playwright/test';
import { isAllowed } from './fixtures';

base('isAllowed treats only the designed statuses as benign', () => {
  // Designed, handled network statuses (ADR-0012/0013/0015) — benign noise.
  for (const status of [401, 404, 409, 422]) {
    expect(
      isAllowed(`Failed to load resource: the server responded with a status of ${status} ()`),
      `status ${status} should be allowlisted`,
    ).toBe(true);
  }
  // A 500 is NEVER designed — including the mock's own "Unmocked path" 500. It must
  // fail the gate, otherwise an app that silently hit a broken/unmocked endpoint would
  // pass a green suite.
  expect(isAllowed('Failed to load resource: the server responded with a status of 500 ()')).toBe(
    false,
  );
  // A 403 is not used by this app (it renders 404-over-403 for privacy) — not benign.
  expect(isAllowed('Failed to load resource: the server responded with a status of 403 ()')).toBe(
    false,
  );
  // The deliberate offline severing in the offline check-in spec (ADR-0030) is
  // benign-by-design ONLY for the spec that opts in via
  // test.use({ allowOfflineNetworkErrors: true }) — a spec WITHOUT the opt-in
  // still fails on that line (the allowance is per-spec, never suite-global)...
  expect(isAllowed('Failed to load resource: net::ERR_INTERNET_DISCONNECTED')).toBe(false);
  expect(
    isAllowed('Failed to load resource: net::ERR_INTERNET_DISCONNECTED', {
      allowOfflineNetworkErrors: true,
    }),
  ).toBe(true);
  // ...and even the opted-in spec is pinned to that exact net-error code; any
  // other network fault (a refused connection = a broken mock/server) fails.
  expect(
    isAllowed('Failed to load resource: net::ERR_CONNECTION_REFUSED', {
      allowOfflineNetworkErrors: true,
    }),
  ).toBe(false);
  expect(isAllowed('Failed to load resource: net::ERR_CONNECTION_REFUSED')).toBe(false);
  expect(isAllowed('Failed to load resource: net::ERR_NAME_NOT_RESOLVED')).toBe(false);
  // Genuine app faults are never allowlisted.
  expect(isAllowed('pageerror: TypeError: foo is not a function')).toBe(false);
  expect(isAllowed('Warning: React does not recognize the `foo` prop on a DOM element')).toBe(
    false,
  );
  expect(isAllowed('Uncaught (in promise) Error: boom')).toBe(false);
});

base('a real thrown error surfaces on the streams the gate listens to', async ({ page }) => {
  const captured: string[] = [];
  page.on('pageerror', (error) => captured.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') captured.push(`console.error: ${message.text()}`);
  });

  // A synchronous throw during script evaluation raises a pageerror the same way an
  // uncaught render/import error in the built bundle would.
  await page.setContent(
    '<!doctype html><meta charset="utf-8"><script>throw new Error("SELF_CHECK_BOOM");</script>',
  );

  await expect
    .poll(() => captured.some((line) => line.includes('SELF_CHECK_BOOM')), {
      message: 'the console gate must observe a real thrown error',
    })
    .toBe(true);

  // And that captured line must NOT be allowlisted — the gate would fail on it.
  const boom = captured.find((line) => line.includes('SELF_CHECK_BOOM'));
  expect(boom).toBeDefined();
  expect(isAllowed(boom as string)).toBe(false);
});
