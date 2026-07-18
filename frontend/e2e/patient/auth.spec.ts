import { expect, test } from '../support/fixtures';
import { installApiMocks, SYNTHETIC_EMAIL, SYNTHETIC_PASSWORD } from '../support/mock-api';

/**
 * These specs use the REAL login/register forms (no seeded session): the form
 * stores the tokens and the in-memory access token, so GET /auth/me succeeds on
 * the first try and the app lands on Home — the genuine sign-in path.
 *
 * They seed the "onboarded" flag (ADR-0044) so the auth landing is tested in
 * isolation; the first-run wizard has its own spec (patient/onboarding.spec.ts).
 */
const ONBOARDED = ['neuropathy.onboarding_complete', '11111111-1111-4111-8111-111111111111'];

test.describe('Auth', () => {
  test('registers a new account and lands on Home', async ({ page }) => {
    await installApiMocks(page);
    await page.addInitScript(([k, id]) => window.localStorage.setItem(k, JSON.stringify([id])), ONBOARDED);
    await page.goto('/register');

    await page.getByLabel('Your name').fill('Pat Example');
    await page.getByLabel('Email').fill(SYNTHETIC_EMAIL);
    await page.getByLabel('Password').fill(SYNTHETIC_PASSWORD);
    await page.getByRole('button', { name: 'Create account' }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('region', { name: 'Your 30 day score' })).toBeVisible();
  });

  test('signs in with valid credentials and lands on Home', async ({ page }) => {
    await installApiMocks(page);
    await page.addInitScript(([k, id]) => window.localStorage.setItem(k, JSON.stringify([id])), ONBOARDED);
    await page.goto('/login');

    await page.getByLabel('Email').fill(SYNTHETIC_EMAIL);
    await page.getByLabel('Password').fill(SYNTHETIC_PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('region', { name: 'Your 30 day score' })).toBeVisible();
  });

  test('shows a friendly error for invalid credentials', async ({ page }) => {
    await installApiMocks(page);
    await page.goto('/login');

    await page.getByLabel('Email').fill(SYNTHETIC_EMAIL);
    await page.getByLabel('Password').fill('the-wrong-passphrase');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('alert')).toContainText(
      "That email or password didn't match. Please try again.",
    );
    // Still on the login screen.
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  });
});
