/**
 * Shared E2E test harness.
 *
 * The core Definition-of-Done gate lives here: `consoleErrors` is an AUTO fixture
 * that attaches to every page's `console` (type==='error') and `pageerror` streams
 * and FAILS the test if any error surfaced. A passing msw/unit test cannot catch a
 * runtime import error, a blank screen, or a thrown exception in the built bundle —
 * this gate does (CLAUDE.md Definition of Done; docs/lessons.md "UI is proven in a
 * real browser").
 *
 * Allowlist: only genuinely-benign, unavoidable noise is ignored. Each pattern is
 * documented inline. The list is intentionally tiny — anything not listed fails.
 */

import { expect, test as base } from '@playwright/test';
import type { Page } from '@playwright/test';
import { installApiMocks, REFRESH_TOKEN_KEY, SYNTHETIC_REFRESH_TOKEN } from './mock-api';
import type { Scenario } from './mock-api';

/**
 * Console-error allowlist — narrow and documented.
 *
 * The ONLY allowed lines are the browser's own automatic "Failed to load resource"
 * network log for the SPECIFIC statuses this app issues by design — and no others.
 * Chromium emits that line for EVERY 4xx/5xx response, so the allowlist is pinned to
 * the exact designed status codes; anything else (notably a 500) still fails the gate:
 *   - 401 on the restore GET /auth/me — the access token is memory-only (ADR-0015),
 *     so a restored session always does exactly one 401 → refresh → retry.
 *   - 409 on PUT /capabilities and POST /adl — optimistic-rollback + feature-off
 *     handling (ADR-0013), surfaced to the user verbatim.
 *   - 404 on /clinic/patients/{id}/* — the neutral 404-over-403 existence privacy
 *     screen (ADR-0012).
 *   - 422 on clinic capability writes — the expiry-without-enable validation message.
 * These are the API contract working as specified; the app renders the correct
 * outcome, which the positive assertions in each spec verify. A GENUINE app fault
 * (uncaught exception, failed module load, React render error, an app-origin
 * console.error, or a 500 — including the mock's own "Unmocked path" 500) is NOT one
 * of these lines: it arrives as a `pageerror`, a different `console.error`, or a
 * non-allowlisted status and still FAILS the gate. `/favicon.ico` is fulfilled 204 by
 * the mock, so it never appears here at all.
 */
const ALLOWED_CONSOLE_PATTERNS: RegExp[] = [
  /Failed to load resource: the server responded with a status of (401|404|409|422)\b/,
];

/**
 * True only for the documented, designed-and-handled network-status noise above.
 * Exported so the self-check spec (support/self-check.spec.ts) can prove the gate
 * both catches real faults and does not false-positive on the allowed statuses.
 */
export function isAllowed(message: string): boolean {
  return ALLOWED_CONSOLE_PATTERNS.some((pattern) => pattern.test(message));
}

interface Fixtures {
  consoleErrors: string[];
}

export const test = base.extend<Fixtures>({
  consoleErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error' && !isAllowed(message.text())) {
          errors.push(`console.error: ${message.text()}`);
        }
      });
      page.on('pageerror', (error) => {
        if (!isAllowed(error.message)) {
          errors.push(`pageerror: ${error.message}`);
        }
      });
      await use(errors);
      // The zero-console-errors gate — the reason this suite exists.
      expect(errors, 'the built app must produce ZERO console errors').toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/**
 * Seed a restored session (patient by default) and install the API mocks, then the
 * next `goto` boots straight into the signed-in app: the token store finds the
 * refresh token in sessionStorage, GET /auth/me 401s (no access token yet), the
 * client refreshes once, and /auth/me returns the account — the REAL restore path.
 */
export async function signedInApp(page: Page, scenario: Scenario = {}): Promise<void> {
  await installApiMocks(page, scenario);
  await page.addInitScript(
    ([key, token]) => {
      window.sessionStorage.setItem(key, token);
    },
    [REFRESH_TOKEN_KEY, SYNTHETIC_REFRESH_TOKEN] as const,
  );
}
