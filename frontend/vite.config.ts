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
