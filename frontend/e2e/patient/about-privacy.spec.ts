import { expect, test } from '../support/fixtures';
import { installApiMocks } from '../support/mock-api';

/**
 * About + Privacy (ADR-0032) in the REAL built bundle, WITHOUT signing in — a store
 * reviewer and a logged-out patient must reach these auth-less routes. Because the
 * route elements are React.lazy (ADR-0032), simply reaching and rendering these
 * pages also exercises the Suspense boundary + lazy chunk load in a real browser;
 * the auto console-error gate (support/fixtures.ts) proves the fallback and the
 * chunk resolve with ZERO console errors. No API calls happen on these pages;
 * `installApiMocks` is used only for its favicon-204 (any stray API call would 500).
 */
test.describe('About & Privacy (auth-less)', () => {
  test('About renders auth-less with version, non-diagnostic disclaimer, and IP line', async ({
    page,
  }) => {
    await installApiMocks(page);
    await page.goto('/about');

    await expect(page.getByRole('heading', { level: 1, name: 'Neuropathy' })).toBeVisible();
    await expect(page.getByText(/Version \d+\.\d+\.\d+/)).toBeVisible();
    await expect(
      page.getByText('Trends support clinical judgment; they are not a diagnosis.'),
    ).toBeVisible();
    await expect(page.getByText(/BioMech Health is a licensee/)).toBeVisible();
  });

  test('Privacy renders as an honest summary that points to the full policy', async ({ page }) => {
    await installApiMocks(page);
    await page.goto('/privacy');

    await expect(
      page.getByRole('heading', { level: 1, name: 'Your privacy, in plain language' }),
    ).toBeVisible();
    await expect(page.getByText(/It is not the complete policy/)).toBeVisible();
    await expect(page.getByRole('heading', { name: 'What we collect' })).toBeVisible();
    await expect(page.getByText(/does not diagnose, treat, or prevent any disease/)).toBeVisible();
  });

  test('cross-links: About ↔ Privacy resolve their lazy chunks in the browser', async ({
    page,
  }) => {
    await installApiMocks(page);
    await page.goto('/about');

    await page.getByRole('link', { name: 'Read the privacy summary' }).click();
    await expect(page).toHaveURL(/\/privacy$/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Your privacy, in plain language' }),
    ).toBeVisible();

    await page.getByRole('link', { name: 'Back to About' }).click();
    await expect(page).toHaveURL(/\/about$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Neuropathy' })).toBeVisible();
  });

  test('the login footer links reach About and Privacy without auth', async ({ page }) => {
    await installApiMocks(page);
    await page.goto('/login');

    await page.getByRole('link', { name: 'Privacy' }).click();
    await expect(page).toHaveURL(/\/privacy$/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Your privacy, in plain language' }),
    ).toBeVisible();
  });
});
