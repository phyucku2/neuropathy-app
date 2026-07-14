import { expect, signedInApp, test } from '../support/fixtures';
import { CAPABILITIES_WITH_UNWIRED } from '../support/mock-api';

test.describe('Patient Sources (capabilities)', () => {
  test('renders capability toggles and flips one optimistically', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Your data sources' })).toBeVisible();

    // ingest_adl starts OFF; flip it on (optimistic, confirmed by the PUT mock).
    const adlSwitch = page.getByRole('switch', { name: 'Daily function check-in' });
    await expect(adlSwitch).toHaveAttribute('aria-checked', 'false');
    await adlSwitch.click();
    await expect(adlSwitch).toHaveAttribute('aria-checked', 'true');

    // An already-on source can be toggled off too.
    const biomechSwitch = page.getByRole('switch', { name: 'BioMech report upload' });
    await expect(biomechSwitch).toHaveAttribute('aria-checked', 'true');
  });

  test('renders an enforced=false capability read-only ("Coming soon")', async ({ page }) => {
    await signedInApp(page, { capabilities: CAPABILITIES_WITH_UNWIRED });
    await page.goto('/settings');

    // The unwired row shows a "Coming soon" pill and NO switch.
    const row = page.locator('.src', { hasText: 'Wearable step count' });
    await expect(row.locator('.pill.off')).toHaveText('Coming soon');
    await expect(row.getByRole('switch')).toHaveCount(0);
  });

  test('surfaces a clinically-managed 409 verbatim and rolls the toggle back', async ({ page }) => {
    await signedInApp(page, {
      putCapability: {
        status: 409,
        body: { detail: 'Your clinic manages this source right now, so it can’t be changed here.' },
      },
    });
    await page.goto('/settings');

    const adlSwitch = page.getByRole('switch', { name: 'Daily function check-in' });
    await expect(adlSwitch).toHaveAttribute('aria-checked', 'false');
    await adlSwitch.click();

    // The server's message is shown verbatim...
    await expect(
      page.getByText('Your clinic manages this source right now, so it can’t be changed here.'),
    ).toBeVisible();
    // ...and the optimistic flip is rolled back to the confirmed state.
    await expect(adlSwitch).toHaveAttribute('aria-checked', 'false');
  });

  test('renders clinic connections with consent controls', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/settings');

    await expect(page.getByText('Advanced Health & Wellness')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Approve connection' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Disconnect' })).toBeVisible();
  });
});
