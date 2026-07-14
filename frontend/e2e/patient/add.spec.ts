import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { expect, signedInApp, test } from '../support/fixtures';

const here = dirname(fileURLToPath(import.meta.url));
const SAMPLE_PDF = join(here, '..', 'fixtures', 'sample-report.pdf');

test.describe('Patient Add data', () => {
  test('renders the BioMech upload UI and imports a report', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/add');

    await expect(page.getByRole('heading', { name: 'Add data', level: 1 })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Upload a balance or gait report' }),
    ).toBeVisible();

    await page.getByLabel('Report PDF').setInputFiles(SAMPLE_PDF);
    await page.getByRole('button', { name: 'Upload report' }).click();

    await expect(page.getByText('3 of 3 values imported from your balance report')).toBeVisible();

    // The EMR connect stub and its clinic connections render.
    await expect(page.getByText('Coming soon').first()).toBeVisible();
    await expect(page.getByText('Regional Medical Center')).toBeVisible();
  });

  test('renders parser warnings as plain text', async ({ page }) => {
    await signedInApp(page, {
      biomech: {
        status: 200,
        body: {
          report_kind: 'gait',
          assessment_at: null,
          imported: 2,
          skipped: 1,
          warnings: [
            'Could not read the cadence value on page 2',
            'Unknown metric "wobble" skipped',
          ],
        },
      },
    });
    await page.goto('/add');

    await page.getByLabel('Report PDF').setInputFiles(SAMPLE_PDF);
    await page.getByRole('button', { name: 'Upload report' }).click();

    await expect(page.getByText('We skipped a few things')).toBeVisible();
    // Warnings are rendered verbatim as list text, never as markup.
    await expect(page.getByText('Could not read the cadence value on page 2')).toBeVisible();
    await expect(page.getByText('Unknown metric "wobble" skipped')).toBeVisible();
  });
});
