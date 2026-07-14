/**
 * Play Store listing screenshots — SYNTHETIC data only (CLAUDE.md §5).
 *
 * Boots the BUILT app (vite build → e2e test config → vite preview, exactly the
 * E2E stack from playwright.config.ts / ADR-0022) and drives it with Playwright's
 * bundled Chromium against the in-browser API mock the E2E suite trusts
 * (e2e/support/mock-api.ts — imported, not duplicated). Every name/value in every
 * screenshot comes from those synthetic fixtures; no real backend, no real data.
 *
 * Output: docs/store-assets/screenshots/*.png at 1080×2400 physical pixels
 * (360×800 CSS viewport at deviceScaleFactor 3 for crispness) — five phone shots:
 * Home (improving trajectory), Trends chart, Check-in, Sources, Clinician trend
 * table.
 *
 * Run from frontend/:  node scripts/generate-store-screenshots.mjs
 * (Requires Node >= 22.18 for native type-stripped import of mock-api.ts.)
 */

import { spawn, execFileSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import {
  installApiMocks,
  CLINICIAN_ME,
  CLINIC_OBSERVATIONS,
  PANEL_PATIENT_ID,
  REFRESH_TOKEN_KEY,
  SYNTHETIC_REFRESH_TOKEN,
} from '../e2e/support/mock-api.ts';

const here = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(here, '..');
const OUT_DIR = join(FRONTEND, '..', 'docs', 'store-assets', 'screenshots');
const PORT = 4318; // matches dist/config.js written by e2e/write-test-config.mjs
const BASE_URL = `http://localhost:${PORT}`;

/**
 * The signedInApp pattern from e2e/support/fixtures.ts: install the API mocks
 * and seed the refresh token so the next `goto` boots straight into the
 * signed-in app through the REAL session-restore path. (fixtures.ts itself uses
 * extensionless imports that plain `node` cannot resolve, so the 4-line pattern
 * is restated here rather than imported.)
 */
async function signedInApp(page, scenario = {}) {
  await installApiMocks(page, scenario);
  await page.addInitScript(
    ([key, token]) => {
      window.sessionStorage.setItem(key, token);
    },
    [REFRESH_TOKEN_KEY, SYNTHETIC_REFRESH_TOKEN],
  );
}

function run(cmd, args) {
  execFileSync(cmd, args, { cwd: FRONTEND, stdio: 'inherit' });
}

async function waitForServer(url, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`preview server did not come up at ${url}`);
}

async function capture(context, name, scenario, drive) {
  const page = await context.newPage();
  await signedInApp(page, scenario);
  await drive(page);
  // Let webfonts and recharts' entry animation fully settle so shots are stable.
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1500);
  const out = join(OUT_DIR, name);
  await page.screenshot({ path: out });
  await page.close();
  console.log(`wrote ${out}`);
}

async function main() {
  // Build the production bundle if it isn't there (idempotent), then point its
  // runtime config at the preview origin — the exact E2E boot path.
  if (!existsSync(join(FRONTEND, 'dist', 'index.html')) || process.env.FORCE_BUILD) {
    run('npm', ['run', 'build']);
  }
  run('node', [join(FRONTEND, 'e2e', 'write-test-config.mjs')]);

  // Detached process group so cleanup kills vite itself, not just the npm
  // wrapper — an orphaned vite would hold port 4318 and poison the next run.
  const preview = spawn('npm', ['run', 'preview'], {
    cwd: FRONTEND,
    stdio: 'ignore',
    detached: true,
  });
  try {
    await waitForServer(BASE_URL);
    mkdirSync(OUT_DIR, { recursive: true });

    const browser = await chromium.launch();
    const context = await browser.newContext({
      baseURL: BASE_URL,
      viewport: { width: 360, height: 800 },
      deviceScaleFactor: 3, // 1080×2400 physical — Play phone-screenshot size
      isMobile: true,
      hasTouch: true,
    });

    // 1. Home — improving trajectory hero (default scenario fixture).
    await capture(context, '01-home-improving.png', {}, async (page) => {
      await page.goto(`${BASE_URL}/`);
      await page.getByText('Improving').first().waitFor();
    });

    // 2. Trends — balance-score line chart with the "better" delta (the default
    // OBSERVATIONS fixture has three balance readings, the richest line).
    await capture(context, '02-trends-chart.png', {}, async (page) => {
      await page.goto(`${BASE_URL}/trends`);
      await page.getByRole('button', { name: 'Balance score' }).click();
      await page.locator('.trend-chart svg').waitFor();
    });

    // 3. Check-in — the three ADL questions, partially answered.
    await capture(context, '03-check-in.png', {}, async (page) => {
      await page.goto(`${BASE_URL}/check-in`);
      const walking = page.getByRole('radiogroup', { name: 'How did walking feel today?' });
      await walking.getByRole('radio').nth(3).click();
      const stairs = page.getByRole('radiogroup', { name: 'How were stairs today?' });
      await stairs.getByRole('radio').nth(2).click();
    });

    // 4. Sources — capability toggles (patient settings).
    await capture(context, '04-sources.png', {}, async (page) => {
      await page.goto(`${BASE_URL}/settings`);
      await page.getByRole('heading', { name: 'Your data sources' }).waitFor();
    });

    // 5. Clinician — patient detail, cross-source trend table.
    await capture(
      context,
      '05-clinician-trend-table.png',
      { me: CLINICIAN_ME, clinicObservations: CLINIC_OBSERVATIONS },
      async (page) => {
        await page.goto(`${BASE_URL}/clinic/patients/${PANEL_PATIENT_ID}`);
        await page.getByRole('button', { name: 'Trend table' }).click();
        await page.getByRole('heading', { name: 'What the data shows' }).waitFor();
      },
    );

    await browser.close();
    console.log('\n5 screenshots generated.');
  } finally {
    try {
      process.kill(-preview.pid, 'SIGTERM');
    } catch {
      preview.kill('SIGTERM');
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
