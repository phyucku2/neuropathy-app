import { expect, signedInApp, test } from '../support/fixtures';

/**
 * The patient Visit-Ready Summary handout (ADR-0045) in the REAL built bundle. The route is
 * React.lazy (ADR-0032), so navigating in exercises the Suspense boundary + lazy chunk load in a
 * real browser; the auto console-error gate (support/fixtures.ts) proves it resolves with ZERO
 * console errors. Also exercises the print seam (stubbed so no dialog opens) and the @media print
 * stylesheet (chrome hidden, disclaimer kept) via emulateMedia.
 */
test.describe('Visit-Ready Summary handout (patient)', () => {
  test('renders the summary, prints without opening a dialog, and hides chrome in print', async ({
    page,
  }) => {
    // Stub window.print BEFORE the app loads so clicking Print never opens a real dialog
    // (which would hang headless Chromium) — the seam still runs, it just no-ops here.
    await page.addInitScript(() => {
      window.print = () => {};
    });
    await signedInApp(page);
    await page.goto('/handout');

    // The page + shared status hero (default 60-day window) + co-located disclaimer. The
    // note is scoped by its text (role="note" carries no accessible name) so a second
    // role="note" landing on this page can never trip a strict-mode collision.
    await expect(page.getByRole('heading', { level: 1, name: 'Visit summary' })).toBeVisible();
    await expect(page.getByRole('region', { name: /Your 60 days summary/ })).toBeVisible();
    const disclaimer = page.getByRole('note').filter({ hasText: 'not a diagnosis' });
    await expect(disclaimer).toBeVisible();

    // Sourced sections render.
    await expect(page.getByRole('heading', { name: 'What changed' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Symptoms' })).toBeVisible();
    await expect(page.getByRole('img', { name: /nerve pain over this window/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Questions to ask' })).toBeVisible();

    // Print must not throw or open a dialog (stubbed above); the page stays put.
    await page.getByRole('button', { name: 'Print or save as PDF' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Visit summary' })).toBeVisible();

    // Print media: the app chrome (status bar + tab bar) is hidden; the disclaimer stays.
    await page.emulateMedia({ media: 'print' });
    await expect(page.locator('.status-bar')).toBeHidden();
    await expect(page.locator('.tabbar')).toBeHidden();
    await expect(disclaimer).toBeVisible();
    await page.emulateMedia({ media: 'screen' });
  });

  test('changes the window from the picker and re-renders', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/handout');
    await expect(page.getByRole('region', { name: /Your 60 days summary/ })).toBeVisible();

    await page.getByRole('button', { name: '1 year' }).click();
    await expect(page.getByRole('region', { name: /Your 1 year summary/ })).toBeVisible();
  });

  test('is reachable from the Sources card', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/settings');
    await page.getByRole('link', { name: 'Open visit summary' }).click();
    await expect(page).toHaveURL(/\/handout$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Visit summary' })).toBeVisible();
  });

  test('renders the EMR clinician notes section as metadata only (ADR-0045 P2 #27)', async ({
    page,
  }) => {
    await signedInApp(page);
    await page.goto('/handout');

    // The notes section renders its metadata (type + author) with an "open it in your
    // medical record" affordance — and NEVER a note body (the summary carries none).
    const section = page
      .locator('section.handout-section')
      .filter({ has: page.getByRole('heading', { name: 'EMR clinician notes' }) });
    await expect(section).toBeVisible();
    await expect(section.getByText('Progress note')).toBeVisible();
    await expect(section.getByText(/Dr\. Rivera/)).toBeVisible();
    await expect(section.getByText(/open it there to read it/)).toBeVisible();
  });
});
