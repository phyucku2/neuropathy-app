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

    // Clicking initiates real file downloads (Blob + object URL). The web path fires
    // BOTH a JSON and a CSV back-to-back in the SAME user gesture, so we attach the
    // listener BEFORE the click and collect every `download` event — asserting only the
    // first would let a regression that drops the CSV pass silently.
    const filenames: string[] = [];
    page.on('download', (download) => filenames.push(download.suggestedFilename()));
    await button.click();

    await expect.poll(() => filenames.length, { timeout: 5000 }).toBe(2);
    const stem = /^neuropathy-export-\d{4}-\d{2}-\d{2}\./;
    expect(filenames.every((name) => stem.test(name))).toBe(true);
    // Both file kinds landed — the JSON (complete form) and the CSV (spreadsheet view).
    expect(filenames.some((name) => name.endsWith('.json'))).toBe(true);
    expect(filenames.some((name) => name.endsWith('.csv'))).toBe(true);

    // The mock backend really served exactly one export, and the success state shows.
    expect(api.dataExports).toBe(1);
    await expect(page.getByText('Your data is ready.')).toBeVisible();
  });
});
