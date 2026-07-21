/**
 * In-browser fetch mock for the self-contained demo build.
 *
 * The REAL app (src/App) talks to the API over `fetch`; there is no backend in a
 * static single-file demo, so we monkeypatch `window.fetch` BEFORE React mounts and
 * fulfil every API pathname from the SAME synthetic fixtures the unit suite trusts
 * (src/test/fixtures.ts — which mirrors e2e/support/mock-api.ts). Any non-API URL
 * (there are none at runtime — fonts/CSS/JS are all inlined) delegates to the
 * original fetch, so nothing else changes.
 *
 * This is a browser-safe re-implementation of the `method + pathname` switch in
 * frontend/e2e/support/mock-api.ts (~lines 428–651). That module cannot be imported
 * here because it pulls in `node:fs`; the DATA, however, is shared via src/test.
 *
 * Synthetic data ONLY. Credential-shaped values stay as the uppercase synthetic
 * constants already used across the codebase.
 */

import type { AdlCheckInIn, CapabilitySetIn, ClinicianCapabilitySetIn } from '../../src/api/types';
import { REFRESH_TOKEN_KEY } from '../../src/auth/refreshTokenBackend';
import {
  CAPABILITIES,
  CAREGIVER_CLAIM_ACCEPTED_DETAIL,
  CAREGIVER_INVITE_CREATE,
  CAREGIVER_LINKS,
  CAREGIVER_ME,
  CAREGIVER_PATIENTS,
  CLINIC_CAPABILITIES,
  CLINICIAN_ME,
  CONNECTION_ACTIVE,
  CONNECTION_PENDING,
  DELETE_WRONG_PASSWORD_DETAIL,
  EMR_AUTH_CODE,
  EMR_CONNECT_START,
  EMR_CONNECTION_ACTIVE,
  EMR_CONNECTION_REVOKED,
  EMR_PROVIDERS,
  EMR_PULL,
  EMR_STATE,
  EXPORT,
  ME,
  OBSERVATIONS,
  PANEL,
  PANEL_PATIENT_ID,
  TEST_ACCESS_TOKEN,
  TEST_EMAIL,
  TEST_PASSWORD,
  TEST_REFRESH_TOKEN,
  TEST_REFRESHED_ACCESS_TOKEN,
  TRAJECTORY_IMPROVING,
  VISIT_SUMMARY,
} from '../../src/test/fixtures';

// ---- demo role (patient / clinician / caregiver) ----------------------------

export type DemoRole = 'patient' | 'clinician' | 'caregiver';

const ROLE_KEY = 'neuropathy-demo.role';

export function currentRole(): DemoRole {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(ROLE_KEY) : null;
  if (stored === 'clinician' || stored === 'caregiver') return stored;
  return 'patient';
}

export function setRole(role: DemoRole): void {
  localStorage.setItem(ROLE_KEY, role);
}

/**
 * Seed a restored session so the app boots straight into the signed-in surface with
 * no login step — exactly like the E2E `signedInApp` harness: the token store finds
 * the refresh token in sessionStorage, GET /auth/me 401s (access token is memory-only),
 * the client refreshes once, and /auth/me returns the account. The REAL restore path.
 */
export function seedSession(): void {
  window.sessionStorage.setItem(REFRESH_TOKEN_KEY, TEST_REFRESH_TOKEN);
}

// ---- fetch shim -------------------------------------------------------------

const JSON_HEADERS = { 'content-type': 'application/json' };

function json(status: number, body: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: JSON_HEADERS,
  });
}

const unauthorized = () => json(401, { detail: 'Not authenticated' });
const patientNotFound = () => json(404, { detail: 'Patient not found' });

function headerFrom(init: RequestInit | undefined, name: string): string | null {
  const h = init?.headers;
  if (!h) return null;
  if (h instanceof Headers) return h.get(name);
  if (Array.isArray(h)) {
    const found = h.find(([k]) => k.toLowerCase() === name.toLowerCase());
    return found ? found[1] : null;
  }
  const rec = h as Record<string, string>;
  return rec[name] ?? rec[name.toLowerCase()] ?? null;
}

function isAuthorized(init: RequestInit | undefined): boolean {
  const header = headerFrom(init, 'authorization');
  return (
    header === `Bearer ${TEST_ACCESS_TOKEN}` || header === `Bearer ${TEST_REFRESHED_ACCESS_TOKEN}`
  );
}

function bodyJson<T>(init: RequestInit | undefined): T {
  const raw = init?.body;
  if (typeof raw === 'string') return JSON.parse(raw) as T;
  return {} as T;
}

/** Slice an observation array into an ObservationPage honouring limit/offset. */
function page(items: typeof OBSERVATIONS, url: URL) {
  const limit = Number(url.searchParams.get('limit') ?? '100');
  const offset = Number(url.searchParams.get('offset') ?? '0');
  return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
}

const tokenBody = () => ({
  access_token: TEST_ACCESS_TOKEN,
  refresh_token: TEST_REFRESH_TOKEN,
  token_type: 'bearer',
});

/**
 * The API_PATH matcher mirrors the mock-api.ts prefix regex: only the app's own API
 * path space is intercepted. Everything else falls through to the original fetch.
 */
const API_PREFIX =
  /^\/(auth|me|observations|adl|biomech|trajectory|capabilities|connections|clinic|caregiver|emr)(\/|$|\?)/;

function handle(method: string, url: URL, init: RequestInit | undefined): Response | null {
  const path = url.pathname;
  if (!API_PREFIX.test(path)) return null;

  const role = currentRole();
  const me = role === 'clinician' ? CLINICIAN_ME : role === 'caregiver' ? CAREGIVER_ME : ME;

  // ---- auth (anonymous endpoints) ----
  if (method === 'POST' && path === '/auth/login') {
    const body = bodyJson<{ email: string; password: string }>(init);
    if (body.email === TEST_EMAIL && body.password === TEST_PASSWORD) {
      return json(200, tokenBody());
    }
    return json(401, { detail: 'Invalid email or password' });
  }
  if (method === 'POST' && path === '/auth/register') {
    return json(201, tokenBody());
  }
  // Caregiver self-registration (ADR-0047) is anonymous — a valid code creates the
  // account; the demo accepts any code and boots the new caregiver signed-in.
  if (method === 'POST' && path === '/caregiver/register') {
    return json(201, tokenBody());
  }
  if (method === 'POST' && path === '/auth/refresh') {
    const body = bodyJson<{ refresh_token: string }>(init);
    if (body.refresh_token === TEST_REFRESH_TOKEN) {
      return json(200, { access_token: TEST_REFRESHED_ACCESS_TOKEN, token_type: 'bearer' });
    }
    return json(401, { detail: 'Invalid token' });
  }

  // ---- everything below requires a valid bearer ----
  if (!isAuthorized(init)) return unauthorized();

  if (method === 'GET' && path === '/auth/me') return json(200, me);
  if (method === 'DELETE' && path === '/auth/me') {
    const body = bodyJson<{ password: string }>(init);
    if (body.password === TEST_PASSWORD) return json(204, null);
    return json(403, { detail: DELETE_WRONG_PASSWORD_DETAIL });
  }
  if (method === 'GET' && path === '/me/export') return json(200, EXPORT);
  if (method === 'GET' && path === '/trajectory') return json(200, TRAJECTORY_IMPROVING);
  if (method === 'GET' && path === '/observations') return json(200, page(OBSERVATIONS, url));

  if (method === 'POST' && path === '/adl') {
    const body = bodyJson<AdlCheckInIn>(init);
    return json(200, {
      check_in_date: '2026-07-13',
      daily_score: body.walking + body.stairs + body.balance_confidence,
      superseded: false,
    });
  }
  if (method === 'POST' && path === '/biomech/reports') {
    return json(200, {
      report_kind: 'balance',
      assessment_at: '2026-07-02T10:00:00Z',
      imported: 3,
      skipped: 0,
      warnings: [],
    });
  }

  if (method === 'GET' && path === '/capabilities')
    return json(200, { capabilities: CAPABILITIES });
  if (method === 'PUT' && /^\/capabilities\/[^/]+$/.test(path)) {
    const key = decodeURIComponent(path.split('/')[2] ?? '');
    const body = bodyJson<CapabilitySetIn>(init);
    const existing = CAPABILITIES.find((row) => row.key === key);
    if (existing === undefined) return json(404, { detail: 'Unknown capability' });
    return json(200, { ...existing, active: body.active });
  }

  if (method === 'GET' && path === '/connections') {
    return json(200, [CONNECTION_PENDING, CONNECTION_ACTIVE]);
  }
  if (method === 'POST' && /^\/connections\/[^/]+\/consent$/.test(path)) {
    return json(200, {
      ...CONNECTION_PENDING,
      status: 'active',
      consent_granted_at: '2026-07-13T12:00:00Z',
    });
  }
  if (method === 'DELETE' && /^\/connections\/[^/]+$/.test(path)) return json(204, null);

  // ---- EMR connect (ADR-0028) ----
  if (method === 'GET' && path === '/emr/providers') {
    const q = (url.searchParams.get('q') ?? '').trim().toLowerCase();
    return json(
      200,
      EMR_PROVIDERS.filter(
        (p) =>
          q === '' ||
          p.key.toLowerCase().includes(q) ||
          p.name.toLowerCase().includes(q) ||
          p.vendor.toLowerCase().includes(q),
      ),
    );
  }
  if (method === 'POST' && path === '/emr/connect') {
    const body = bodyJson<{ provider_key?: string | null }>(init);
    if (body.provider_key === 'meditech') {
      return json(422, { detail: 'Provider has no public sandbox; supply fhir_base explicitly' });
    }
    return json(200, EMR_CONNECT_START);
  }
  if (method === 'GET' && path === '/emr/callback') {
    if (
      url.searchParams.get('state') !== EMR_STATE ||
      url.searchParams.get('code') !== EMR_AUTH_CODE
    ) {
      return json(404, { detail: 'Unknown, expired, or already-used state' });
    }
    return json(200, EMR_CONNECTION_ACTIVE);
  }
  if (method === 'POST' && /^\/emr\/connections\/[^/]+\/pull$/.test(path))
    return json(200, EMR_PULL);
  if (method === 'DELETE' && /^\/emr\/connections\/[^/]+$/.test(path)) {
    return json(200, EMR_CONNECTION_REVOKED);
  }

  // ---- clinician surface ----
  if (method === 'POST' && path === '/clinic/invitations') {
    return json(202, {
      detail: 'If this email belongs to a patient account, an invitation is now pending.',
    });
  }
  if (method === 'GET' && path === '/clinic/patients') return json(200, PANEL);

  const patientMatch = /^\/clinic\/patients\/([^/]+)\/(trajectory|observations|capabilities)$/.exec(
    path,
  );
  if (method === 'GET' && patientMatch) {
    const id = decodeURIComponent(patientMatch[1] ?? '');
    if (id !== PANEL_PATIENT_ID) return patientNotFound();
    const kind = patientMatch[2];
    if (kind === 'trajectory') return json(200, TRAJECTORY_IMPROVING);
    if (kind === 'observations') return json(200, page(OBSERVATIONS, url));
    return json(200, { capabilities: CLINIC_CAPABILITIES });
  }

  const putCapMatch = /^\/clinic\/patients\/([^/]+)\/capabilities\/([^/]+)$/.exec(path);
  if (method === 'PUT' && putCapMatch) {
    const id = decodeURIComponent(putCapMatch[1] ?? '');
    const key = decodeURIComponent(putCapMatch[2] ?? '');
    const body = bodyJson<ClinicianCapabilitySetIn>(init);
    if (!body.active && body.expires_at != null) {
      return json(422, {
        detail: [
          {
            type: 'value_error',
            loc: ['body'],
            msg: 'Value error, expires_at only applies when active=true; omit it when disabling',
          },
        ],
      });
    }
    if (id !== PANEL_PATIENT_ID) return patientNotFound();
    const existing = CLINIC_CAPABILITIES.find((row) => row.key === key);
    if (existing === undefined) return json(404, { detail: 'Unknown capability' });
    return json(200, { ...existing, active: body.active, expires_at: body.expires_at ?? null });
  }

  // ---- caregiver companion (ADR-0047 Phase A) ----

  // Patient side — the "Share with a loved one" card (patient Settings/Sources).
  if (method === 'GET' && path === '/me/caregiver-invites') return json(200, []);
  if (method === 'POST' && path === '/me/caregiver-invites')
    return json(201, CAREGIVER_INVITE_CREATE);
  if (method === 'DELETE' && /^\/me\/caregiver-invites\/[^/]+$/.test(path)) return json(204, null);

  if (method === 'GET' && path === '/me/caregivers') return json(200, CAREGIVER_LINKS);
  if (method === 'POST' && /^\/me\/caregivers\/[^/]+\/accept$/.test(path)) {
    const id = decodeURIComponent(path.split('/')[3] ?? '');
    const link = CAREGIVER_LINKS.find((l) => l.id === id);
    if (link === undefined) return patientNotFound();
    return json(200, { ...link, status: 'active', accepted_at: '2026-07-21T10:00:00Z' });
  }
  if (method === 'POST' && /^\/me\/caregivers\/[^/]+\/decline$/.test(path)) return json(204, null);
  if (method === 'PATCH' && /^\/me\/caregivers\/[^/]+$/.test(path)) {
    const id = decodeURIComponent(path.split('/')[3] ?? '');
    const link = CAREGIVER_LINKS.find((l) => l.id === id);
    if (link === undefined) return patientNotFound();
    const body = bodyJson<{ scope?: string }>(init);
    return json(200, { ...link, scope: body.scope ?? link.scope });
  }
  if (method === 'DELETE' && /^\/me\/caregivers\/[^/]+$/.test(path)) return json(204, null);

  // Caregiver side — claim a code + read the shared patient's trend/summary.
  if (method === 'POST' && path === '/caregiver/claims') {
    return json(202, { detail: CAREGIVER_CLAIM_ACCEPTED_DETAIL });
  }
  if (method === 'GET' && path === '/caregiver/patients') return json(200, CAREGIVER_PATIENTS);
  const caregiverReadMatch = /^\/caregiver\/patients\/([^/]+)\/(trajectory|visit-summary)$/.exec(
    path,
  );
  if (method === 'GET' && caregiverReadMatch) {
    const id = decodeURIComponent(caregiverReadMatch[1] ?? '');
    // Only the shared patient is readable; anyone else is 404 (never 403) — the
    // server's non-enumeration posture, mirrored here.
    if (id !== PANEL_PATIENT_ID) return patientNotFound();
    return caregiverReadMatch[2] === 'trajectory'
      ? json(200, TRAJECTORY_IMPROVING)
      : json(200, VISIT_SUMMARY);
  }

  // Any unmatched API path is a demo bug — surface it rather than hang.
  return json(500, { detail: `Unmocked ${method} ${path}` });
}

let installed = false;

/** Monkeypatch window.fetch. Call once, BEFORE React mounts. */
export function installDemoMock(): void {
  if (installed) return;
  installed = true;
  const originalFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    let method = init?.method ?? 'GET';
    let urlString: string;
    let effectiveInit = init;

    if (input instanceof Request) {
      urlString = input.url;
      method = init?.method ?? input.method;
      // The app never routes API calls through a Request object, but be correct anyway.
      effectiveInit = init ?? {
        method: input.method,
        headers: input.headers,
      };
    } else {
      urlString = input instanceof URL ? input.toString() : String(input);
    }

    let url: URL;
    try {
      url = new URL(urlString, window.location.href);
    } catch {
      return originalFetch(input as RequestInfo, init);
    }

    const response = handle(method.toUpperCase(), url, effectiveInit);
    if (response !== null) return response;
    return originalFetch(input as RequestInfo, init);
  };
}
