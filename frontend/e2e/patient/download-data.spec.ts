/**
 * "Download my data" (ADR-0031) against the BUILT bundle.
 *
 * Proves the right-of-access card renders in Settings (above the danger zone) and the
 * web download path actually fires in a real browser: clicking the button hits the
 * mocked GET /me/export and initiates a real Blob download (a Playwright `download`
 * event) — the thing a passing msw unit test cannot prove. Zero console errors.
 */

import { expect, signedInApp, test } from '../support/fixtures';

test.describe('Patient data export (Download my data)', () => {
  test('renders the card and initiates a real download in the browser', async ({ page }) => {
    const api = await signedInApp(page);
    await page.goto('/settings');

    // The card sits above the danger zone, clearly separated ("Your data", distinct
    // from the page's own "Your data sources" heading).
    await expect(page.getByRole('heading', { name: 'Your data', exact: true })).toBeVisible();
    const button = page.getByRole('button', { name: 'Download my data' });
    await expect(button).toBeVisible();

    // Clicking initiates a real file download (Blob + object URL). Web triggers both a
    // JSON and a CSV; waiting on the first download event proves the path fired.
    const [download] = await Promise.all([page.waitForEvent('download'), button.click()]);
    expect(download.suggestedFilename()).toMatch(
      /^neuropathy-export-\d{4}-\d{2}-\d{2}\.(json|csv)$/,
    );

    // The mock backend really served exactly one export, and the success state shows.
    expect(api.dataExports).toBe(1);
    await expect(page.getByText('Your data is ready.')).toBeVisible();
  });
});
