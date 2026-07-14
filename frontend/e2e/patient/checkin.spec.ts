import { expect, signedInApp, test } from '../support/fixtures';
import type { Page } from '@playwright/test';

/**
 * Answer one 0-4 ADL question via the KEYBOARD radiogroup (WAI-ARIA pattern):
 * focus the first radio, then ArrowRight `value` times — each press moves focus
 * AND selects, proving the roving-tabindex + arrow-select behavior in a real
 * browser.
 */
async function answerByKeyboard(page: Page, groupName: string, value: number): Promise<void> {
  const group = page.getByRole('radiogroup', { name: groupName });
  await group.getByRole('radio').first().focus();
  for (let i = 0; i < value; i += 1) {
    await page.keyboard.press('ArrowRight');
  }
  // The nth radio (0-indexed == the answer value) is now selected — arrow keys
  // both move focus and select in the WAI-ARIA radiogroup pattern.
  await expect(group.getByRole('radio').nth(value)).toBeChecked();
}

test.describe('Patient Check-in', () => {
  test('submits the three ADL answers by keyboard and shows the score', async ({ page }) => {
    await signedInApp(page);
    await page.goto('/check-in');

    await answerByKeyboard(page, 'How did walking feel today?', 3);
    await answerByKeyboard(page, 'How were stairs today?', 2);
    await answerByKeyboard(page, 'How confident did you feel about your balance?', 4);

    await page.getByRole('button', { name: 'Save my check-in' }).click();

    await expect(page.getByRole('heading', { name: 'Check-in saved' })).toBeVisible();
    // 3 + 2 + 4 = 9 of 12.
    await expect(page.getByText('9 of 12')).toBeVisible();
  });

  test('shows the superseded notice on a same-day re-submission', async ({ page }) => {
    await signedInApp(page, {
      adl: { status: 200, body: { superseded: true } },
    });
    await page.goto('/check-in');

    await answerByKeyboard(page, 'How did walking feel today?', 1);
    await answerByKeyboard(page, 'How were stairs today?', 1);
    await answerByKeyboard(page, 'How confident did you feel about your balance?', 1);
    await page.getByRole('button', { name: 'Save my check-in' }).click();

    await expect(page.getByText('This replaces the check-in you already did today')).toBeVisible();
  });

  test('surfaces the feature-off (409) handling verbatim', async ({ page }) => {
    await signedInApp(page, {
      adl: { status: 409, body: { detail: 'This check-in is turned off right now.' } },
    });
    await page.goto('/check-in');

    await answerByKeyboard(page, 'How did walking feel today?', 2);
    await answerByKeyboard(page, 'How were stairs today?', 2);
    await answerByKeyboard(page, 'How confident did you feel about your balance?', 2);
    await page.getByRole('button', { name: 'Save my check-in' }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('This check-in is turned off right now.');
    // The feature-off path offers the route back to Sources.
    await expect(alert.getByRole('link', { name: /turn it back on in Sources/ })).toBeVisible();
  });
});
