import { defineConfig } from '@playwright/test';

/**
 * E2E config (ADR-0022): drive the BUILT production bundle in a real Chromium.
 *
 * - `webServer` runs `vite build`, writes a test `/config.js` (ADR-0018 runtime
 *   config), then `vite preview` — so tests hit the SAME artifact we ship, not the
 *   dev server, and boot through the real runtime-config path.
 * - The browser is the pre-installed Chromium at PLAYWRIGHT_BROWSERS_PATH
 *   (=/opt/pw-browsers); the pinned @playwright/test version matches that build, so
 *   no `playwright install` / download is needed locally.
 */

const PORT = 4318;
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    // Deterministic viewport (the patient UI is a mobile-width column; give the
    // charts real dimensions to render into).
    viewport: { width: 900, height: 1000 },
  },
  projects: [
    {
      // The pre-installed Chromium (rev 1194) — no branded channel, no download.
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: {
    command: 'npm run build && node e2e/write-test-config.mjs && npm run preview',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
