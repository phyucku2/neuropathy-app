import { expect, signedInApp, test } from '../support/fixtures';
import { CLINICIAN_ME, PANEL_EMPTY } from '../support/mock-api';

test.describe('Clinician Panel', () => {
  test('renders the consented patients and marks the clinician frame', async ({ page }) => {
    await signedInApp(page, { me: CLINICIAN_ME });
    await page.goto('/clinic');

    await expect(page.getByRole('heading', { name: 'Your panel' })).toBeVisible();
    await expect(page.getByText('◍ Neuropathy · Clinician')).toBeVisible();
    // Both consented patients appear.
    await expect(page.getByText('Pat Example')).toBeVisible();
    await expect(page.getByText('Jordan Marsh')).toBeVisible();
  });

  test('renders the empty-panel state', async ({ page }) => {
    await signedInApp(page, { me: CLINICIAN_ME, panel: PANEL_EMPTY });
    await page.goto('/clinic');

    await expect(page.getByText('No consented patients yet.')).toBeVisible();
  });

  test('shows the non-enumerating invite confirmation', async ({ page }) => {
    await signedInApp(page, { me: CLINICIAN_ME });
    await page.goto('/clinic');

    await page.getByLabel('Patient email').fill('someone@example.com');
    await page.getByRole('button', { name: 'Send invitation' }).click();

    // ONE fixed sentence for every outcome — the UI never reveals whether the
    // email matched a patient account (ADR-0012 non-enumeration).
    await expect(
      page.getByText("If that email belongs to a patient account, they'll receive an invitation."),
    ).toBeVisible();
  });
});
