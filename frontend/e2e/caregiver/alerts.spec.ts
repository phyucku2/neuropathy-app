/**
 * Caregiver Alerts feed E2E (ADR-0047 B1): the real built app, in a Chromium, driving
 * the compute-on-read feed the caregiver reads — reached from the caregiver home, listed
 * with the non-urgent / 911 framing co-located, acknowledged in one tap. And the scope
 * gate: a trends-only caregiver never sees a med / chart-note alert, not even its
 * existence. Every caregiver screen carries the persistent 911 banner.
 */

import { expect, signedInApp, test } from '../support/fixtures';
import {
  activeCaregiverLink,
  CAREGIVER_ME,
  newCaregiverStore,
  seedCaregiverAlert,
} from '../support/mock-api';

const BANNER_TEXT = "If something's wrong right now, call 911.";

test.describe('Caregiver Alerts feed (ADR-0047 B1)', () => {
  test('full scope: reached from the home, lists updates with the 911 framing, acknowledges one', async ({
    page,
  }) => {
    const store = newCaregiverStore();
    store.links.push(activeCaregiverLink('full'));
    store.alerts.push(seedCaregiverAlert('missed_checkin'), seedCaregiverAlert('med_change'));
    await signedInApp(page, { me: CAREGIVER_ME, caregiverStore: store });

    // Reached from the caregiver home (the area has no tab bar).
    await page.goto('/caregiver');
    await page.getByRole('link', { name: 'See your updates' }).click();
    await expect(page.getByRole('heading', { name: 'Updates' })).toBeVisible();

    // Both full-scope alerts render their fixed, non-diagnostic template copy.
    await expect(page.getByText('A check-in was missed')).toBeVisible();
    await expect(page.getByText('A medication update')).toBeVisible();
    // The non-urgent framing is co-located beside the list AND in the shell banner.
    await expect(page.getByText(/not a diagnosis, and not live monitoring/)).toBeVisible();
    await expect(page.getByText(BANNER_TEXT).first()).toBeVisible();

    // Two unacknowledged rows → two "Got it" buttons; acking one leaves one.
    await expect(page.getByRole('button', { name: 'Got it' })).toHaveCount(2);
    await page.getByRole('button', { name: 'Got it' }).first().click();
    await expect(page.getByRole('button', { name: 'Got it' })).toHaveCount(1);
    await expect(page.getByText('Seen')).toBeVisible();
  });

  test('trends scope: a med / chart-note alert never surfaces (no scope leak)', async ({
    page,
  }) => {
    const store = newCaregiverStore();
    store.links.push(activeCaregiverLink('trends'));
    store.alerts.push(
      seedCaregiverAlert('missed_checkin'),
      seedCaregiverAlert('med_change'),
      seedCaregiverAlert('new_chart_note'),
    );
    await signedInApp(page, { me: CAREGIVER_ME, caregiverStore: store });

    await page.goto('/caregiver/alerts');
    await expect(page.getByRole('heading', { name: 'Updates' })).toBeVisible();

    // The trends-allowed alert shows; the full-only alerts are absent entirely.
    await expect(page.getByText('A check-in was missed')).toBeVisible();
    await expect(page.getByText('A medication update')).toHaveCount(0);
    await expect(page.getByText('A new note from the care team')).toHaveCount(0);
    await expect(page.getByText(BANNER_TEXT).first()).toBeVisible();
  });

  test('empty feed: the all-caught-up state, with the framing still present', async ({ page }) => {
    const store = newCaregiverStore();
    store.links.push(activeCaregiverLink('full'));
    await signedInApp(page, { me: CAREGIVER_ME, caregiverStore: store });

    await page.goto('/caregiver/alerts');
    await expect(page.getByRole('heading', { name: 'No updates right now' })).toBeVisible();
    await expect(page.getByText(BANNER_TEXT).first()).toBeVisible();
  });
});
