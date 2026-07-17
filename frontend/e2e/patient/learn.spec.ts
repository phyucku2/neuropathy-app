import { expect, signedInApp, test } from '../support/fixtures';

/**
 * Learn (ADR-0037) in the REAL built bundle. The route element is React.lazy (ADR-0032),
 * so reaching and rendering the page also exercises the Suspense boundary + lazy chunk
 * load in a real browser; the auto console-error gate (support/fixtures.ts) proves the
 * fallback and the chunk resolve with ZERO console errors. The page makes NO API calls —
 * its modules come from the local placeholder registry — so `signedInApp` is used only to
 * boot the signed-in patient shell (the real /auth/me restore path).
 */
test.describe('Learn (education modules)', () => {
  test('renders the module index with the intro, module titles, and the disclaimer', async ({
    page,
  }) => {
    await signedInApp(page);
    await page.goto('/learn');

    await expect(page.getByRole('heading', { level: 1, name: 'Learn' })).toBeVisible();
    await expect(page.getByText(/Short, plain-language lessons/)).toBeVisible();

    // Evidence-first lead + a couple more module titles.
    await expect(
      page.getByRole('heading', { level: 2, name: 'Exercise & balance training' }),
    ).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Foot care' })).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: 'When to call your care team' }),
    ).toBeVisible();

    // Placeholder states + the standard non-diagnostic disclaimer (ADR-0037).
    await expect(page.getByText('Next session ▶')).toBeVisible();
    await expect(page.getByText('Reviewed by your care team')).toBeVisible();
    await expect(
      page.getByText('General education — not medical advice. Talk to your care team.'),
    ).toBeVisible();
  });

  test('is reachable from the bottom-nav Learn tab', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/');
    await page.getByRole('region', { name: 'Your 30 day score' }).waitFor();

    const nav = page.getByRole('navigation', { name: 'Main' });
    await nav.getByRole('link', { name: /Learn/ }).click();
    await expect(page).toHaveURL(/\/learn$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Learn' })).toBeVisible();
  });
});
