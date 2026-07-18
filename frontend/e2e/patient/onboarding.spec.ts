import { expect, signedInApp, test } from '../support/fixtures';

test.describe('First-run onboarding (ADR-0044)', () => {
  test('a not-yet-onboarded patient sees the welcome, then enters the app', async ({ page }) => {
    // Opt OUT of the harness's default "onboarded" seed to exercise the first-run gate.
    await signedInApp(page, {}, { onboarded: false });
    await page.goto('/');

    // The full-screen welcome renders (no bottom tab bar yet).
    await expect(page.getByRole('heading', { name: 'A clearer picture, over time' })).toBeVisible();
    await expect(page.getByText('Step 1 of 3')).toBeVisible();

    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByRole('heading', { name: 'Easy to use, and yours' })).toBeVisible();
    await page.getByRole('button', { name: 'Get started' }).click();

    // The app (home) now renders; the wizard is gone.
    await expect(page.getByText('30 Day Score')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'A clearer picture, over time' })).toHaveCount(
      0,
    );
  });

  test('a returning (onboarded) patient boots straight into the app', async ({ page }) => {
    await signedInApp(page); // default: onboarded
    await page.goto('/');
    await expect(page.getByText('30 Day Score')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'A clearer picture, over time' })).toHaveCount(
      0,
    );
  });
});
