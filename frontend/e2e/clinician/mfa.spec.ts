import { expect, signedInApp, test } from '../support/fixtures';
import {
  CLINICIAN_ME,
  installApiMocks,
  SYNTHETIC_MFA_CODE,
  SYNTHETIC_MFA_SECRET,
  SYNTHETIC_PASSWORD,
} from '../support/mock-api';

test.describe('Clinician MFA (TOTP, §1B C6)', () => {
  test('enrolls an authenticator from the clinician Settings card', async ({ page }) => {
    await signedInApp(page, { me: CLINICIAN_ME });
    await page.goto('/clinic');

    await page.getByRole('link', { name: 'Settings' }).click();
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

    await page.getByRole('button', { name: 'Set up two-step verification' }).click();
    // The one-time secret showing: URI + secret, with the shown-once warning.
    await expect(page.getByLabel('Secret key (manual entry)')).toHaveValue(SYNTHETIC_MFA_SECRET);
    await expect(page.getByText('it is shown only once')).toBeVisible();

    await page.getByLabel('6-digit code from your app').fill(SYNTHETIC_MFA_CODE);
    await page.getByRole('button', { name: 'Turn on two-step verification' }).click();

    // The factor is live; the secret is gone (shown once, never again).
    await expect(
      page.getByText('Signing in requires a code from your authenticator app.'),
    ).toBeVisible();
    await expect(page.getByLabel('Secret key (manual entry)')).toHaveCount(0);
  });

  test('an enrolled clinician signs in through the TOTP step-up', async ({ page }) => {
    await installApiMocks(page, { me: CLINICIAN_ME, mfa: { enrolled: true } });
    await page.goto('/login');

    await page.getByLabel('Email').fill(CLINICIAN_ME.email);
    await page.getByLabel('Password').fill(SYNTHETIC_PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();

    // Password success alone lands on the step-up, not in the app.
    await expect(page.getByRole('heading', { name: 'Two-step verification' })).toBeVisible();

    await page.getByLabel('6-digit code').fill(SYNTHETIC_MFA_CODE);
    await page.getByRole('button', { name: 'Verify' }).click();

    await expect(page.getByRole('heading', { name: 'Your panel' })).toBeVisible();
  });
});
