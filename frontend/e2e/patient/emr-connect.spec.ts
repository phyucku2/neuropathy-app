/**
 * EMR connect round trip in the BUILT bundle (ADR-0028): Sources → provider picker →
 * connect (the mocked authorize URL points back at the app's own /emr/callback with
 * code+state, simulating the EMR redirect without leaving the origin) → the
 * authenticated callback relay → active connection → pull → two-tap revoke.
 *
 * The full-page navigation to the authorize URL exercises the REAL web OAuth path:
 * the SPA reboots on /emr/callback, restores the session (the designed 401 → refresh),
 * validates the persisted state, and relays code+state to the bearer-only backend
 * callback. Zero console errors (the auto gate in support/fixtures.ts).
 */

import { expect, signedInApp, test } from '../support/fixtures';

test.describe('Patient EMR connect (SMART round trip)', () => {
  test('connects a provider, relays the callback, pulls labs, and revokes', async ({ page }) => {
    const state = await signedInApp(page);
    await page.goto('/settings');

    // The card sits with the connection cards, NOT inside the danger zone.
    await expect(page.getByRole('heading', { name: 'Health record connections' })).toBeVisible();

    // Provider picker with the real server-side search behavior.
    await page.getByLabel('Search for your provider').fill('mychart');
    await expect(page.getByText('MEDITECH')).toHaveCount(0);
    const connectButton = page.getByRole('button', { name: 'Connect Epic (MyChart)' });
    await expect(connectButton).toBeVisible();

    // Connect: POST /emr/connect → persist pending state → full-page redirect to the
    // authorize URL, which the mock points back at our own /emr/callback?code=..&state=..
    await connectButton.click();
    await page.waitForURL(/\/emr\/callback\?code=/);

    // The relay completed against the backend: provider, status, and actions render.
    await expect(page.getByText('Epic (MyChart)')).toBeVisible();
    await expect(page.getByText('Connected', { exact: true })).toBeVisible();

    // Pull labs now.
    await page.getByRole('button', { name: 'Pull labs now' }).click();
    await expect(page.getByText('Imported 2 of 2 lab results into your record.')).toBeVisible();
    expect(state.emrPulls).toBe(1);

    // Revoke is two-tap: the first tap arms, the second revokes.
    await page.getByRole('button', { name: 'Disconnect' }).click();
    await expect(page.getByRole('button', { name: 'Tap again to confirm' })).toBeVisible();
    expect(state.emrRevocations).toBe(0);
    await page.getByRole('button', { name: 'Tap again to confirm' }).click();
    await expect(page.getByText('Disconnected', { exact: true })).toBeVisible();
    expect(state.emrRevocations).toBe(1);
    await expect(page.getByRole('button', { name: 'Pull labs now' })).toHaveCount(0);

    // And back to Sources.
    await page.getByRole('link', { name: 'Back to Sources' }).click();
    await expect(page.getByRole('heading', { name: 'Your data sources' })).toBeVisible();
  });
});
