import { expect, signedInApp, test } from '../support/fixtures';
import type { Page } from '@playwright/test';

/**
 * Offline check-in queue (ADR-0030) in the BUILT bundle:
 * submit while offline → captured on-device with a saved-on-this-device status →
 * connectivity returns → the queue flushes automatically (window 'online' event)
 * and the mock backend really receives the POST with the entry's true local date.
 *
 * Offline is simulated two ways AT ONCE, deliberately:
 * - `context.setOffline(true/false)` drives `navigator.onLine` and fires the real
 *   window 'online' event on restore — the app's actual sync trigger.
 * - the /adl route is aborted with 'internetdisconnected' while offline, because
 *   Playwright route interception can still FULFILL mocked responses under
 *   emulated offline (interception sits in front of the network stack); the abort
 *   guarantees the same fetch TypeError a genuinely offline browser produces.
 * The resulting "Failed to load resource: net::ERR_INTERNET_DISCONNECTED" console
 * line is benign-by-design FOR THIS SPEC ONLY (the failure is the scenario, and the
 * app handles it — proven by the assertions below): this spec opts in via
 * `test.use({ allowOfflineNetworkErrors: true })`, the allowance stays pinned to
 * that exact net-error code, and every other spec keeps failing on the line
 * (ADR-0022 discipline — never a broad or suite-global pattern).
 */

async function answerByKeyboard(page: Page, groupName: string, value: number): Promise<void> {
  const group = page.getByRole('radiogroup', { name: groupName });
  await group.getByRole('radio').first().focus();
  for (let i = 0; i < value; i += 1) {
    await page.keyboard.press('ArrowRight');
  }
  await expect(group.getByRole('radio').nth(value)).toBeChecked();
}

/** The browser's LOCAL calendar day — same machine/TZ as this test process. */
function localDay(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${String(now.getFullYear())}-${month}-${day}`;
}

// The ONLY spec allowed to log the deliberate offline net-error (see fixtures.ts).
test.use({ allowOfflineNetworkErrors: true });

test.describe('Patient Check-in — offline queue', () => {
  test('captures an offline submission on-device and syncs it when back online', async ({
    page,
    context,
  }) => {
    const state = await signedInApp(page);
    await page.goto('/check-in');

    await answerByKeyboard(page, 'How did walking feel today?', 3);
    await answerByKeyboard(page, 'How were stairs today?', 2);
    await answerByKeyboard(page, 'How confident did you feel about your balance?', 4);

    // Sever the network (see the header comment for why both mechanisms).
    await context.setOffline(true);
    await page.route('**/adl', (route) => route.abort('internetdisconnected'));

    await page.getByRole('button', { name: 'Save my check-in' }).click();

    // The distinct success-variant state: captured, not lost — and not an error.
    await expect(
      page.getByRole('heading', { name: 'Check-in saved on this device' }),
    ).toBeVisible();
    await expect(page.getByRole('status')).toHaveText(
      "Saved on this device — will send automatically when you're back online.",
    );
    expect(state.adlPosts).toEqual([]); // nothing reached the API while offline

    // Connectivity returns: setOffline(false) fires the real window 'online'
    // event, which is the app's automatic flush trigger — no reload, no click.
    await page.unroute('**/adl');
    await context.setOffline(false);

    // The UI reflects the synced result (the server's real response: 3+2+4 = 9).
    await expect(page.getByRole('heading', { name: 'Check-in saved' })).toBeVisible();
    await expect(page.getByText('9 of 12')).toBeVisible();

    // The mock backend RECORDED the flushed POST, carrying the answers and the
    // TRUE local capture date — never re-dated (ADR-0030 honest-data rule).
    expect(state.adlPosts).toEqual([
      { walking: 3, stairs: 2, balance_confidence: 4, check_in_date: localDay() },
    ]);

    // And the on-device queue is empty again (cleared on sync).
    const stored = await page.evaluate(() =>
      window.localStorage.getItem('neuropathy.offline_checkins'),
    );
    expect(stored).toBeNull();
  });
});
