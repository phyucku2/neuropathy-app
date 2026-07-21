import { expect, signedInApp, test } from '../support/fixtures';

/**
 * Patient-entered capture (ADR-0045 P2) in the REAL built bundle: the medication change-log and
 * the between-visit notes/events surfaces, plus their appearance in the Visit-Ready Summary
 * handout. Both routes are React.lazy (ADR-0032), so navigating in exercises the Suspense
 * boundary + lazy chunk load; the auto console-error gate (support/fixtures.ts) proves ZERO
 * console errors. The API mock is stateful, so an added med / recorded event shows up on GET.
 */
test.describe('Medications & between-visit events (patient)', () => {
  test('adds a supplement, records a fall, and sees both in the handout', async ({ page }) => {
    await signedInApp(page);

    // ---- Medications: the list starts empty, then an add shows up ----
    await page.goto('/meds');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Medications & supplements' }),
    ).toBeVisible();
    // Co-located non-diagnostic disclaimer — scoped by its text (role="note" carries no
    // accessible name) so a second role="note" on this page never trips strict mode.
    await expect(
      page.getByRole('note').filter({ hasText: 'never adjusts, checks, or recommends' }),
    ).toBeVisible();
    await expect(
      page.getByText('Nothing on your list yet. Add your first medication above.'),
    ).toBeVisible();

    await page.getByLabel('Name').fill('Alpha-lipoic acid');
    await page.getByLabel('Kind').selectOption('supplement');
    await page.getByLabel('Dose amount (optional)').fill('600');
    await page.getByLabel('Dose unit (optional)').fill('mg');
    await page.getByRole('button', { name: 'Add to my list' }).click();

    await expect(page.getByText('Added Alpha-lipoic acid to your list.')).toBeVisible();
    // The added medication now renders as an active row (folded from GET /medications). Exact
    // match so it doesn't also collide with the success-notice text above.
    await expect(page.getByText('Alpha-lipoic acid', { exact: true })).toBeVisible();
    await expect(page.getByText('Active')).toBeVisible();

    // ---- Events: the persistent emergency banner + record a fall ----
    await page.goto('/events');
    await expect(page.getByRole('heading', { level: 1, name: 'Notes & events' })).toBeVisible();
    const banner = page.getByRole('note', { name: 'Emergency information' });
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('not monitored in real time');

    await page.getByLabel('What happened?').selectOption('fall');
    await page.getByLabel(/Note \(optional/).fill('Lost my balance stepping off the curb.');
    await page.getByRole('button', { name: 'Save' }).click();

    await expect(page.getByText('Saved to your between-visit list.')).toBeVisible();
    await expect(page.getByText('Lost my balance stepping off the curb.')).toBeVisible();
    await expect(page.getByText(/In your own words:/)).toBeVisible();

    // ---- Handout: the medication + the fall render under their captured sections ----
    await page.goto('/handout');
    await expect(page.getByRole('heading', { level: 1, name: 'Visit summary' })).toBeVisible();
    const meds = page.getByRole('heading', { name: 'Medications & supplements' });
    await expect(meds).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Patient notes & events' })).toBeVisible();
    // Exact + section-scoped: a substring 'Fall' would also match any question/data-gap
    // wording that happens to contain "fall(s)".
    const eventsSection = page
      .locator('section.handout-section')
      .filter({ has: page.getByRole('heading', { name: 'Patient notes & events' }) });
    await expect(eventsSection.getByText('Fall', { exact: true })).toBeVisible();
    // The what-changed medication delta is descriptive only.
    await expect(
      page.getByRole('heading', { name: 'Medications recorded this window' }),
    ).toBeVisible();
  });

  test('is reachable from the Add data cards', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/add');
    await page.getByRole('link', { name: 'Open medications' }).click();
    await expect(page).toHaveURL(/\/meds$/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Medications & supplements' }),
    ).toBeVisible();

    await page.goto('/add');
    await page.getByRole('link', { name: 'Open notes & events' }).click();
    await expect(page).toHaveURL(/\/events$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Notes & events' })).toBeVisible();
  });
});
