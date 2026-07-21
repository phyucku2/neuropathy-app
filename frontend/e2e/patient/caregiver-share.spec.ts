/**
 * Patient-side "Share with a loved one" card E2E (ADR-0047): invite-code
 * generation and cancel, the double opt-in accept/decline choice, plain-words
 * scope control, and the instant two-tap revoke — the patient controls everything.
 */

import { expect, signedInApp, test } from '../support/fixtures';
import { activeCaregiverLink, newCaregiverStore, pendingCaregiverLink } from '../support/mock-api';

test.describe('Share with a loved one (patient card)', () => {
  test('creates an invite code (shown once, with expiry) and cancels it', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Share with a loved one' })).toBeVisible();
    const card = page.locator('.card', { hasText: 'Give a family member or friend' });
    // Plain-language control + non-monitoring framing on the card itself.
    await expect(
      card.getByText(/not live monitoring, and it is not for emergencies/),
    ).toBeVisible();

    await card.getByRole('button', { name: 'Create an invite code' }).click();
    const code = await card.locator('.invite-code').innerText();
    expect(code).not.toEqual('');
    await expect(card.getByText(/works once and expires/)).toBeVisible();
    await expect(card.getByText(/won't be shown again/)).toBeVisible();

    // The invite is listed (without its code) and can be cancelled — the code dies.
    await expect(card.getByText('Open invites')).toBeVisible();
    await card.getByRole('button', { name: 'Cancel' }).click();
    await expect(card.getByText('Open invites')).toHaveCount(0);
  });

  test('accepts a pending request, changes scope in plain words, then revokes (two-tap)', async ({
    page,
  }) => {
    const store = newCaregiverStore();
    store.links.push(pendingCaregiverLink('Casey Example'));
    await signedInApp(page, { caregiverStore: store });
    await page.goto('/settings');

    // The pending request names the caregiver; nothing is shared until the patient says yes.
    await expect(page.getByText('Waiting for your OK')).toBeVisible();
    await expect(page.getByText(/Nothing is shared until you say yes/)).toBeVisible();
    await page.getByRole('button', { name: 'Yes, share with Casey Example' }).click();

    // Accepted: active with the default trends-only scope, in plain words.
    await expect(page.getByText('Sharing with')).toBeVisible();
    await expect(page.getByText('Can see their trend only')).toBeVisible();

    // Widen to full scope...
    await page.getByRole('button', { name: 'Also share your visit summary' }).click();
    await expect(page.getByText('Can see their trend and your visit summary')).toBeVisible();
    // ...and narrow it back down.
    await page.getByRole('button', { name: 'Limit to trend only' }).click();
    await expect(page.getByText('Can see their trend only')).toBeVisible();

    // Revoke needs the confirm tap; then the caregiver is gone instantly.
    await page.getByRole('button', { name: 'Stop sharing' }).click();
    await expect(page.getByRole('button', { name: 'Tap again to confirm' })).toBeVisible();
    await page.getByRole('button', { name: 'Tap again to confirm' }).click();
    await expect(page.getByText('Sharing with')).toHaveCount(0);
  });

  test('declines a pending request without ever sharing', async ({ page }) => {
    const store = newCaregiverStore();
    store.links.push(pendingCaregiverLink('Casey Example'));
    await signedInApp(page, { caregiverStore: store });
    await page.goto('/settings');

    await expect(page.getByText('Waiting for your OK')).toBeVisible();
    await page.getByRole('button', { name: 'No, decline' }).click();
    await expect(page.getByText('Waiting for your OK')).toHaveCount(0);
    // Declined ≠ shared: no active caregiver appears.
    await expect(page.getByText('Sharing with')).toHaveCount(0);
  });

  test('an active caregiver row shows the scope on load', async ({ page }) => {
    const store = newCaregiverStore();
    store.links.push(activeCaregiverLink('full', 'Robin Example'));
    await signedInApp(page, { caregiverStore: store });
    await page.goto('/settings');

    await expect(page.getByText('Sharing with')).toBeVisible();
    await expect(page.getByText('Robin Example')).toBeVisible();
    await expect(page.getByText('Can see their trend and your visit summary')).toBeVisible();
  });

  // Per-type caregiver-alert opt-ins (ADR-0047 B1) — the sibling card, DEFAULT OFF.
  test('turns a caregiver-alert type on (default OFF) and it persists', async ({ page }) => {
    const store = newCaregiverStore();
    await signedInApp(page, { caregiverStore: store });
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Updates you send to loved ones' })).toBeVisible();
    const toggle = page.getByRole('switch', { name: 'Medication updates' });
    // Everything is off until the patient turns it on.
    await expect(toggle).toHaveAttribute('aria-checked', 'false');
    await toggle.click();
    await expect(page.getByRole('switch', { name: 'Medication updates' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    // The store recorded the opt-in (the mock backend's real statefulness).
    expect(store.preferences.med_change).toBe(true);
  });
});
