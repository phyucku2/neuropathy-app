/**
 * Write the E2E test runtime config into the built bundle (ADR-0018 / ADR-0022).
 *
 * The production build ships `dist/config.js` with an EMPTY (same-origin) apiBaseUrl.
 * This script overwrites it with an explicit apiBaseUrl so the boot path genuinely
 * exercises reading a per-deployment value from `window.__APP_CONFIG__` — the same
 * mechanism the container entrypoint uses at deploy time. The base points back at the
 * preview origin, so requests stay same-origin and are intercepted by the in-browser
 * API mock (e2e/support/mock-api.ts). Contains NO secrets — a local base URL only.
 */

import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const target = join(here, '..', 'dist', 'config.js');

writeFileSync(
  target,
  '// E2E test runtime config (ADR-0022) — synthetic, no secrets.\n' +
    "window.__APP_CONFIG__ = { apiBaseUrl: 'http://localhost:4318' };\n",
);
