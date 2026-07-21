/**
 * Danger zone — account & data deletion (ADR-0027) against the BUILT bundle.
 *
 * Proves the full flow in a real browser: expand the danger zone, re-type the
 * password, acknowledge permanent deletion, pass the two-tap confirm, and land on
 * the login screen with the transient confirmation — with the mock API having
 * actually received the deletion (204, so no console-error noise; the wrong-password
 * 403 shape lives in mock-api.ts and is exercised by the unit suite).
 */

import { expect, signedInApp, test } from '../support/fixtures';
import { SYNTHETIC_PASSWORD } from '../support/mock-api';

test.describe('Patient account deletion (danger zone)', () => {
  test('deletes the account end to end and lands on the login screen', async ({ page }) => {
    const api = await signedInApp(page);
    await page.goto('/settings');

    // The danger zone sits at the bottom of Settings, collapsed by default.
    await expect(page.getByRole('heading', { name: 'Danger zone' })).toBeVisible();
    await page.getByRole('button', { name: 'Delete my account' }).click();

    // The confirm stays disabled until BOTH the password and the acknowledgment
    // are supplied.
    const confirm = page.getByRole('button', { name: 'Delete my account and data' });
    await expect(confirm).toBeDisabled();
    await page.getByLabel('Confirm your password').fill(SYNTHETIC_PASSWORD);
    await expect(confirm).toBeDisabled();
    // Scoped by name: Settings now has other checkboxes (e.g. the EMR notes
    // opt-in from #27), so a bare getByRole('checkbox') is ambiguous.
    await page.getByRole('checkbox', { name: /permanently deleted/ }).check();
    await expect(confirm).toBeEnabled();

    // Two-tap confirm: the first tap only arms the button — nothing deleted yet.
    await confirm.click();
    expect(api.accountDeletions).toBe(0);
    await page.getByRole('button', { name: 'Tap again to permanently delete' }).click();

    // The session is gone: the login screen with the transient deleted notice.
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await expect(page.getByText('Your account and data were deleted.')).toBeVisible();
    // The mock backend really received (and honored) exactly one deletion.
    expect(api.accountDeletions).toBe(1);
    // The refresh token is cleared — a reload stays signed out on /login.
    const stored = await page.evaluate(() => window.sessionStorage.length);
    expect(stored).toBe(0);
  });
});
