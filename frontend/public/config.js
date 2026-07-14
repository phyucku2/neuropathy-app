// Runtime app config (ADR-0018). This DEFAULT ships in the image and points the app at
// the SAME ORIGIN (nginx reverse-proxies the API). The container entrypoint
// (frontend/docker-entrypoint.sh) OVERWRITES this file at START time from the
// API_BASE_URL env var, so one immutable image serves any environment without a
// rebuild. Contains NO secrets — a public API base URL only.
window.__APP_CONFIG__ = { apiBaseUrl: '' };
