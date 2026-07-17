import { expect, signedInApp, test } from '../support/fixtures';

/**
 * Your Records (read-only, display-only) in the REAL built bundle. The route element is
 * React.lazy (ADR-0032), so navigating in from Sources and rendering the page exercises
 * the Suspense boundary + lazy chunk load in a real browser; the auto console-error gate
 * (support/fixtures.ts) proves it resolves with ZERO console errors. The default mock
 * observations include two EMR-sourced rows so the record shows real content.
 */
test.describe('Your Records (read-only health record)', () => {
  test('navigates from Sources to Records and shows EMR rows + placeholders', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/settings');

    // Enter from the Sources card — NOT a bottom-nav tab (five is the accessible max).
    await expect(page.getByRole('heading', { name: 'Your records' })).toBeVisible();
    await page.getByRole('link', { name: 'View your records' }).click();
    await expect(page).toHaveURL(/\/records$/);

    await expect(page.getByRole('heading', { level: 1, name: 'Your records' })).toBeVisible();

    // EMR-sourced records render read-only with value+unit and provenance.
    const glucose = page.locator('.record', { hasText: 'Glucose' });
    await expect(glucose).toContainText('101 mg/dL');
    await expect(glucose).toContainText('from your health record');
    await expect(page.locator('.record', { hasText: 'Vitamin B12' })).toContainText('420 pg/mL');

    // Display-only: no interpretation / judged direction / metric picker on this surface.
    await expect(page.getByText(/is better for this measure/)).toHaveCount(0);
    await expect(page.getByRole('group', { name: 'Pick a measure' })).toHaveCount(0);

    // "Coming soon" placeholders for the classes we don't pull yet.
    await expect(page.getByRole('heading', { level: 2, name: 'Conditions' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Medications' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Allergies' })).toBeVisible();
    await expect(page.getByText('Coming soon')).toHaveCount(3);

    // The read-only, non-diagnostic disclaimer.
    await expect(
      page.getByText(/This is a read-only copy of your health record, not medical advice/),
    ).toBeVisible();
  });

  test('shows the gentle connect prompt when medical-record connections are off', async ({
    page,
  }) => {
    const capabilitiesOff = (await import('../support/mock-api')).CAPABILITIES.map((c) =>
      c.key === 'emr_connect' ? { ...c, active: false } : c,
    );
    await signedInApp(page, { capabilities: capabilitiesOff });
    await page.goto('/records');

    await expect(page.getByText('No health record connected yet.')).toBeVisible();
    const back = page.getByRole('link', { name: 'Go to Sources' });
    await expect(back).toBeVisible();
    await back.click();
    await expect(page).toHaveURL(/\/settings$/);
  });
});
