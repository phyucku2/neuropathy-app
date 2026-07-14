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
 * The ONLY allowed pattern is the browser's own automatic "Failed to load resource"
 * network log. Chromium emits this for EVERY HTTP response with a 4xx/5xx status,
 * regardless of whether the app handles it. In this app those statuses are all
 * DESIGNED, handled paths, not defects:
 *   - 401 on the restore GET /auth/me — the access token is memory-only (ADR-0015),
 *     so a restored session always does exactly one 401 → refresh → retry.
 *   - 409 on PUT /capabilities and POST /adl — optimistic-rollback + feature-off
 *     handling (ADR-0013), surfaced to the user verbatim.
 *   - 404 on /clinic/patients/{id}/* — the neutral 404-over-403 existence privacy
 *     screen (ADR-0012).
 *   - 422 on clinic capability writes — the expiry-without-enable validation message.
 * These are the API contract working as specified; the app renders the correct
 * outcome, which the positive assertions in each spec verify. A GENUINE app fault
 * (uncaught exception, failed module load, React render error, or any app-origin
 * console.error) is NOT a "Failed to load resource" line — it arrives as a
 * `pageerror` or a different `console.error` and still FAILS the gate. `/favicon.ico`
 * is fulfilled 204 by the mock, so it never appears here at all.
 */
const ALLOWED_CONSOLE_PATTERNS: RegExp[] = [
  /Failed to load resource: the server responded with a status of \d+/,
];

function isAllowed(message: string): boolean {
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
