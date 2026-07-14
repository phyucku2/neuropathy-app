import { expect, signedInApp, test } from '../support/fixtures';
import { TRAJECTORY_DECLINING, TRAJECTORY_INSUFFICIENT } from '../support/mock-api';

test.describe('Patient Home', () => {
  test('renders the improving trajectory hero, sourced signals, and data gaps', async ({
    page,
  }) => {
    await signedInApp(page);
    await page.goto('/');

    const hero = page.getByRole('region', { name: 'Your 30-day trend' });
    await expect(hero).toBeVisible();
    await expect(hero.getByText('Improving')).toBeVisible();
    await expect(
      hero.getByText('Balance and daily function are up. One lab is worth a look.'),
    ).toBeVisible();
    // Confidence meter is present and spoken.
    await expect(hero.getByRole('img', { name: /Confidence 72 percent/ })).toBeVisible();
    // Deterministic — no AI badge.
    await expect(page.getByText('AI-written summary')).toHaveCount(0);

    // Sourced signals (What's driving it).
    await expect(page.getByText("What's driving it")).toBeVisible();
    await expect(page.getByText('Balance score')).toBeVisible();
    await expect(page.getByRole('img', { name: 'improving' }).first()).toBeVisible();

    // Data gaps card.
    await expect(page.getByText('Data gaps')).toBeVisible();
    await expect(page.getByText('No lab results in the last 90 days')).toBeVisible();
  });

  test('renders the declining variant and the "not enough data" signal state', async ({ page }) => {
    await signedInApp(page, { trajectory: TRAJECTORY_DECLINING });
    await page.goto('/');

    const hero = page.getByRole('region', { name: 'Your 30-day trend' });
    await expect(hero.getByText('Declining')).toBeVisible();
    // The insufficient_data signal must show "not enough data", never a fake "stable".
    await expect(page.getByRole('img', { name: 'not enough data' })).toBeVisible();
    await expect(page.getByRole('img', { name: 'stable' })).toHaveCount(0);
  });

  test('renders the whole-account insufficient_data state', async ({ page }) => {
    await signedInApp(page, { trajectory: TRAJECTORY_INSUFFICIENT });
    await page.goto('/');

    const hero = page.getByRole('region', { name: 'Your 30-day trend' });
    await expect(hero.getByText('Not enough data yet', { exact: true })).toBeVisible();
    await expect(hero.getByText('There is not enough data yet to judge a trend.')).toBeVisible();
    // No signals card when there are no signals.
    await expect(page.getByText("What's driving it")).toHaveCount(0);
  });
});
