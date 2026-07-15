import { fileURLToPath } from 'node:url';
import { defineConfig } from '@playwright/test';

/**
 * Isolated Playwright config for capturing demo screenshots. Kept OUT of the default
 * CI run (`npm run e2e` uses ../playwright.config.ts, testDir ./e2e). This config's
 * testDir is ./demo, so `npx playwright test --config demo/playwright.demo.config.ts`
 * runs only the capture spec. It drives the REAL built app against the E2E mock-API
 * (synthetic data), so every screenshot is a genuine render, not a mockup.
 */
const BASE_URL = 'http://localhost:4318';

export default defineConfig({
  testDir: '.',
  testMatch: '**/capture.spec.ts',
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: BASE_URL,
    viewport: { width: 900, height: 1000 },
    deviceScaleFactor: 2,
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  webServer: {
    command: 'npm run build && node e2e/write-test-config.mjs && npm run preview',
    // Run from the frontend root (this config lives in ./demo), so the relative
    // build/preview/config paths resolve the same way the default e2e config does.
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
