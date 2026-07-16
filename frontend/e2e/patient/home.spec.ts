import { expect, signedInApp, test } from '../support/fixtures';
import { TRAJECTORY_DECLINING, TRAJECTORY_INSUFFICIENT } from '../support/mock-api';

test.describe('Patient Home', () => {
  test('renders the Neuropathy Status Index hero, sourced signals, and data gaps', async ({
    page,
  }) => {
    await signedInApp(page);
    await page.goto('/');

    const hero = page.getByRole('region', { name: 'Your 30 day score' });
    await expect(hero).toBeVisible();
    // Number-forward card: big score, direction word + glyph, delta.
    await expect(hero.getByText('74')).toBeVisible();
    await expect(hero.getByText('/100')).toBeVisible();
    await expect(hero.getByText('improving')).toBeVisible();
    await expect(hero.getByText('+7 pts')).toBeVisible();
    await expect(hero.getByText(/vs 30 days ago/)).toBeVisible();
    await expect(hero.getByText('Confidence: High')).toBeVisible();
    await expect(hero.getByText(/as of Jul 12/)).toBeVisible();

    // Sourced signals (What's driving it) — all three domains present.
    await expect(page.getByText("What's driving it")).toBeVisible();
    await expect(page.getByText('Balance score')).toBeVisible();
    await expect(page.getByText('nerve pain', { exact: true })).toBeVisible();
    await expect(page.getByRole('img', { name: 'declining' }).first()).toBeVisible();

    // Data gaps card.
    await expect(page.getByText('Data gaps')).toBeVisible();
    await expect(page.getByText('No lab results in the last 90 days')).toBeVisible();
  });

  test('renders the declining variant and the "not enough data" signal state', async ({ page }) => {
    await signedInApp(page, { trajectory: TRAJECTORY_DECLINING });
    await page.goto('/');

    const hero = page.getByRole('region', { name: 'Your 30 day score' });
    // Card colour + arrow + word all driven by the negative composite delta.
    await expect(hero).toHaveClass(/declining/);
    await expect(hero.getByText('declining')).toBeVisible();
    await expect(hero.getByText('−6 pts')).toBeVisible();
    // The insufficient_data signal must show "not enough data", never a fake "stable".
    await expect(page.getByRole('img', { name: 'not enough data' })).toBeVisible();
    await expect(page.getByRole('img', { name: 'stable' })).toHaveCount(0);
  });

  test('renders the whole-account insufficient_data state', async ({ page }) => {
    await signedInApp(page, { trajectory: TRAJECTORY_INSUFFICIENT });
    await page.goto('/');

    const hero = page.getByRole('region', { name: 'Your 30 day score' });
    await expect(hero.getByText('Not enough data yet', { exact: true })).toBeVisible();
    // No signals card when there are no signals.
    await expect(page.getByText("What's driving it")).toHaveCount(0);
  });
});
