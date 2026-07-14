import { expect, signedInApp, test } from '../support/fixtures';
import { OBSERVATIONS_TRENDS } from '../support/mock-api';

test.describe('Patient Trends', () => {
  test('renders a line chart with an axis/units summary and delta states', async ({ page }) => {
    await signedInApp(page, { observations: OBSERVATIONS_TRENDS });
    await page.goto('/trends');

    await expect(page.getByRole('heading', { name: 'Trends', level: 1 })).toBeVisible();

    // Balance score: higher-is-better, rising 60 -> 68 = "better".
    await page.getByRole('button', { name: 'Balance score' }).click();
    const betterChart = page.getByRole('img', { name: /Balance score: 2 readings/ });
    await expect(betterChart).toBeVisible();
    // The accessible chart summary carries the unit and the direction.
    await expect(betterChart).toHaveAttribute('aria-label', /rising from 60 to 68 score/);
    await expect(page.getByLabel('up 8 — improving')).toBeVisible();
    await expect(page.getByText('Higher is better for this measure.')).toBeVisible();
    // A real SVG axis was drawn (recharts).
    await expect(page.locator('.trend-chart svg')).toBeVisible();

    // Sway velocity: lower-is-better, rising 9 -> 13 = "worse".
    await page.getByRole('button', { name: 'Sway velocity' }).click();
    await expect(page.getByLabel('up 4 — getting worse')).toBeVisible();
    await expect(page.getByText('Lower is better for this measure.')).toBeVisible();
  });

  test('shows the unit-changed state instead of a delta', async ({ page }) => {
    await signedInApp(page, { observations: OBSERVATIONS_TRENDS });
    await page.goto('/trends');

    await page.getByRole('button', { name: 'Hemoglobin A1c' }).click();
    await expect(page.getByText('unit changed — change not judged')).toBeVisible();
    // No better/worse delta badge is shown when the units are incomparable.
    await expect(page.getByLabel(/improving|getting worse/)).toHaveCount(0);
  });

  test('shows the <2-point empty state for a single-reading metric', async ({ page }) => {
    await signedInApp(page, { observations: OBSERVATIONS_TRENDS });
    await page.goto('/trends');

    await page.getByRole('button', { name: 'Gait speed' }).click();
    await expect(
      page.getByText('Not enough readings to draw a trend yet — one more and the line appears.'),
    ).toBeVisible();
    // No chart is drawn for a single point.
    await expect(page.locator('.trend-chart')).toHaveCount(0);
  });

  test('shows the no-readings empty state', async ({ page }) => {
    await signedInApp(page, { observations: [] });
    await page.goto('/trends');

    await expect(page.getByText('No readings yet.')).toBeVisible();
    await expect(page.locator('.trend-chart')).toHaveCount(0);
  });
});
