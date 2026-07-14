/**
 * Runtime API base URL resolution (ADR-0018).
 *
 * Vite inlines `import.meta.env.*` at BUILD time, so a value baked into the bundle
 * cannot vary per environment without a rebuild. To ship ONE immutable frontend image
 * to many environments, the container entrypoint writes `/config.js` at container
 * START time (see frontend/docker-entrypoint.sh), which sets:
 *
 *     window.__APP_CONFIG__ = { apiBaseUrl: 'https://api.example.org' };
 *
 * `index.html` loads `/config.js` before the app bundle, so the value is present by
 * the time any request is made. Resolution order (first non-empty wins):
 *
 *   1. window.__APP_CONFIG__.apiBaseUrl  — runtime, set per deployment (no rebuild)
 *   2. import.meta.env.VITE_API_BASE_URL — build-time fallback (dev convenience)
 *   3. ''                                 — same-origin (nginx reverse-proxies the API)
 */

export interface AppRuntimeConfig {
  apiBaseUrl?: string;
}

declare global {
  interface Window {
    __APP_CONFIG__?: AppRuntimeConfig;
  }
}

/** The API base URL for this deployment, resolved fresh so runtime config always wins. */
export function apiBaseUrl(): string {
  const runtime = window.__APP_CONFIG__?.apiBaseUrl;
  if (typeof runtime === 'string' && runtime.length > 0) {
    return runtime;
  }
  const buildTime = import.meta.env.VITE_API_BASE_URL as string | undefined;
  return buildTime ?? '';
}
