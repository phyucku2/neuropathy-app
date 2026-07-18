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
import type { MockApiState, Scenario } from './mock-api';

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
 * PER-SPEC opt-in (never suite-global): the offline check-in spec
 * (patient/checkin-offline.spec.ts, ADR-0030) drives a DESIGNED offline
 * submission — the POST /adl is deliberately severed (context.setOffline +
 * route.abort('internetdisconnected')), Chromium logs this exact network line for
 * the failed resource, and the app HANDLES the failure (the fetch TypeError is
 * caught and the check-in is queued on-device; the spec's positive assertions
 * prove it). That spec opts in with `test.use({ allowOfflineNetworkErrors: true })`;
 * every other spec keeps failing on this line, and even the opted-in spec is
 * pinned to this one net-error code — a different network fault (e.g.
 * net::ERR_CONNECTION_REFUSED, a genuinely broken mock) still fails the gate.
 */
const OFFLINE_NETWORK_ERROR_PATTERN = /Failed to load resource: net::ERR_INTERNET_DISCONNECTED\b/;

/**
 * True only for the documented, designed-and-handled network noise: the allowed
 * statuses everywhere, plus the offline net-error line ONLY when the calling
 * spec opted in (see OFFLINE_NETWORK_ERROR_PATTERN). Exported so the self-check
 * spec (support/self-check.spec.ts) can prove the gate catches real faults, does
 * not false-positive on the allowed statuses, and keeps the offline line failing
 * for specs WITHOUT the opt-in.
 */
export function isAllowed(
  message: string,
  options: { allowOfflineNetworkErrors?: boolean } = {},
): boolean {
  if (options.allowOfflineNetworkErrors === true && OFFLINE_NETWORK_ERROR_PATTERN.test(message)) {
    return true;
  }
  return ALLOWED_CONSOLE_PATTERNS.some((pattern) => pattern.test(message));
}

interface Fixtures {
  consoleErrors: string[];
  /** Spec-scoped opt-in (test.use) for the deliberate-offline scenario only. */
  allowOfflineNetworkErrors: boolean;
}

export const test = base.extend<Fixtures>({
  allowOfflineNetworkErrors: [false, { option: true }],
  consoleErrors: [
    async ({ page, allowOfflineNetworkErrors }, use) => {
      const errors: string[] = [];
      page.on('console', (message) => {
        if (
          message.type() === 'error' &&
          !isAllowed(message.text(), { allowOfflineNetworkErrors })
        ) {
          errors.push(`console.error: ${message.text()}`);
        }
      });
      page.on('pageerror', (error) => {
        if (!isAllowed(error.message, { allowOfflineNetworkErrors })) {
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
export async function signedInApp(
  page: Page,
  scenario: Scenario = {},
  { onboarded = true }: { onboarded?: boolean } = {},
): Promise<MockApiState> {
  const state = await installApiMocks(page, scenario);
  await page.addInitScript(
    ([key, token]) => {
      window.sessionStorage.setItem(key, token);
    },
    [REFRESH_TOKEN_KEY, SYNTHETIC_REFRESH_TOKEN] as const,
  );
  // First-run welcome gate (ADR-0044): seed the per-user "onboarded" flag so specs boot
  // straight into the app, like a returning patient. The onboarding spec passes
  // { onboarded: false } to exercise the wizard. The id matches the mock patient's user_id.
  if (onboarded) {
    await page.addInitScript(([key, userId]) => {
      window.localStorage.setItem(key, JSON.stringify([userId]));
    }, ['neuropathy.onboarding_complete', '11111111-1111-4111-8111-111111111111'] as const);
  }
  return state;
}
