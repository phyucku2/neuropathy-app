import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// The backend mounts its routes at the root (no /api prefix), so the dev server
// proxies each API path prefix to the local FastAPI instance. At runtime the app
// talks ONLY to these endpoints — no third-party requests ever (ADR-0015).
const API_PREFIXES = [
  '/auth',
  '/observations',
  '/adl',
  '/labs',
  '/biomech',
  '/trajectory',
  '/capabilities',
  '/connections',
  '/clinic',
  // NOTE: /emr is both an API prefix (POST /emr/connect, GET /emr/providers, ...) and
  // a client route (/emr/callback, the SMART relay) — the same shared-prefix situation
  // as /clinic (ADR-0022): fetch/XHR goes to the API, document navigations render the
  // SPA (the E2E mock serves index.html for them; in dev, land on the SPA via an
  // in-app navigation).
  '/emr',
];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      API_PREFIXES.map((prefix) => [prefix, { target: 'http://localhost:8000' }]),
    ),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    restoreMocks: true,
    // Run test FILES one at a time. Component tests that mount the app + drive msw are sensitive
    // to cross-file CPU/scheduler contention: with enough parallel worker files, an unrelated
    // `findBy*` intermittently loses its element (a fast detach/timing race, not a slow render, so
    // a longer async timeout does not help). Serializing files makes the jsdom suite deterministic
    // (~a few extra seconds) — tests within a file still run normally. (ADR-0024 review finding.)
    fileParallelism: false,
    // Vitest owns the src unit/component suite; the Playwright E2E specs under
    // e2e/ (also *.spec.ts) run in a real browser and MUST NOT be collected here.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      exclude: ['src/main.tsx', 'src/test/**', 'src/**/*.test.*', 'src/vite-env.d.ts'],
      thresholds: {
        lines: 90,
        branches: 90,
        functions: 90,
        statements: 90,
      },
    },
  },
});
