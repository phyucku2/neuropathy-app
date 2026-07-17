import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from '@playwright/test';
import { installApiMocks } from '../e2e/support/mock-api';
import { signedInApp } from '../e2e/support/fixtures';
import {
  CAPABILITIES_SYMPTOMS_ON,
  CLINICIAN_ME,
  PANEL_PATIENT_ID,
  TRAJECTORY_DECLINING,
} from '../e2e/support/mock-api';

/**
 * Captures a real screenshot of each major screen of the BUILT app, served from the
 * E2E mock-API on synthetic data. Output PNGs feed build-demo-html.mjs, which embeds
 * them into a single self-contained walkthrough (docs/business/demo/app-demo.html).
 *
 * Not a gate — this file lives under ./demo and only runs via
 * `npx playwright test --config demo/playwright.demo.config.ts`.
 */
const SHOTS = resolve(dirname(fileURLToPath(import.meta.url)), 'shots');
mkdirSync(SHOTS, { recursive: true });

async function shot(page: import('@playwright/test').Page, name: string): Promise<void> {
  // Let fonts/charts settle so the capture is crisp.
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${SHOTS}/${name}.png` });
}

test('capture — patient login', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/login');
  await page
    .getByRole('button', { name: /sign in/i })
    .first()
    .waitFor();
  await shot(page, '01-login');
});

test('capture — patient home (improving trend)', async ({ page }) => {
  await signedInApp(page);
  await page.goto('/');
  await page.getByRole('region', { name: 'Your 30 day score' }).waitFor();
  await shot(page, '02-home-improving');
});

test('capture — patient home (declining trend)', async ({ page }) => {
  await signedInApp(page, { trajectory: TRAJECTORY_DECLINING });
  await page.goto('/');
  await page.getByRole('region', { name: 'Your 30 day score' }).waitFor();
  await shot(page, '03-home-declining');
});

test('capture — trends', async ({ page }) => {
  await signedInApp(page);
  await page.goto('/trends');
  await page.waitForLoadState('networkidle');
  await shot(page, '04-trends');
});

test('capture — learn', async ({ page }) => {
  await signedInApp(page);
  await page.goto('/learn');
  await page.getByRole('heading', { level: 1, name: 'Learn' }).waitFor();
  await shot(page, '04b-learn');
});

test('capture — daily check-in', async ({ page }) => {
  // Symptom capture ON so the demo check-in shows all three domains' inputs
  // (function questions + pain + numbness), matching the full 3-domain NSI card.
  await signedInApp(page, { capabilities: CAPABILITIES_SYMPTOMS_ON });
  await page.goto('/check-in');
  await page.waitForLoadState('networkidle');
  await shot(page, '05-checkin');
});

test('capture — add data', async ({ page }) => {
  await signedInApp(page);
  await page.goto('/add');
  await page.waitForLoadState('networkidle');
  await shot(page, '06-add');
});

test('capture — sources & settings', async ({ page }) => {
  await signedInApp(page);
  await page.goto('/settings');
  await page.waitForLoadState('networkidle');
  await shot(page, '07-settings');
});

test('capture — your records', async ({ page }) => {
  await signedInApp(page);
  await page.goto('/records');
  await page.getByRole('heading', { level: 1, name: 'Your records' }).waitFor();
  await page.waitForLoadState('networkidle');
  await shot(page, '07b-records');
});

test('capture — about', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/about');
  await page.waitForLoadState('networkidle');
  await shot(page, '08-about');
});

test('capture — clinician panel', async ({ page }) => {
  await signedInApp(page, { me: CLINICIAN_ME });
  await page.goto('/clinic');
  await page.getByRole('heading', { name: 'Your panel' }).waitFor();
  await shot(page, '09-clinician-panel');
});

test('capture — clinician patient detail', async ({ page }) => {
  await signedInApp(page, { me: CLINICIAN_ME });
  await page.goto(`/clinic/patients/${PANEL_PATIENT_ID}`);
  await page.waitForLoadState('networkidle');
  await shot(page, '10-clinician-patient-detail');
});
