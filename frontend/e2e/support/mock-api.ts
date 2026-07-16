/**
 * In-browser API mocks for the E2E suite.
 *
 * The built SPA talks to the API over `fetch`; there is no live backend here, so
 * every API call is intercepted with Playwright's `page.route` and fulfilled from
 * fixtures that MIRROR `src/test/fixtures.ts` + `src/test/server.ts` (the msw
 * contract the unit suite already trusts). Keeping the shapes identical means the
 * browser exercises the SAME response bodies the real API would return, so a render
 * that passes here would pass against the backend.
 *
 * Synthetic data ONLY (CLAUDE.md §5). Credential-shaped values are uppercase
 * SYNTHETIC_ constants, never real secrets (docs/lessons.md).
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Page, Route } from '@playwright/test';
import type {
  CapabilityStateOut,
  ConnectionOut,
  EmrConnectionOut,
  EmrProviderOut,
  EmrPullOut,
  ExportObservation,
  ExportOut,
  MeOut,
  ObservationItem,
  PanelOut,
  Trajectory,
} from '../../src/api/types';

// ---- synthetic credentials + tokens (mirror src/test/fixtures.ts) ----

export const SYNTHETIC_EMAIL = 'pat.example@example.com';
export const SYNTHETIC_PASSWORD = 'synthetic-test-passphrase';

/** The real backend's DELETE /auth/me wrong-password detail (ADR-0027), verbatim. */
export const DELETE_WRONG_PASSWORD_DETAIL = "That password didn't match. Nothing was deleted.";
const SYNTHETIC_ACCESS_TOKEN = 'synthetic-access-token';
const SYNTHETIC_REFRESHED_ACCESS_TOKEN = 'synthetic-access-token-2';
export const SYNTHETIC_REFRESH_TOKEN = 'synthetic-refresh-token';

/** sessionStorage key the token store uses (src/auth/tokenStore.ts). */
export const REFRESH_TOKEN_KEY = 'neuropathy.refresh_token';

function isAuthorized(route: Route): boolean {
  const header = route.request().headers()['authorization'];
  return (
    header === `Bearer ${SYNTHETIC_ACCESS_TOKEN}` ||
    header === `Bearer ${SYNTHETIC_REFRESHED_ACCESS_TOKEN}`
  );
}

// ---- patient fixtures ----

export const ME: MeOut = {
  user_id: '11111111-1111-4111-8111-111111111111',
  email: SYNTHETIC_EMAIL,
  display_name: 'Pat Example',
  role: 'patient',
  patient_id: '22222222-2222-4222-8222-222222222222',
};

export const CLINICIAN_ME: MeOut = {
  user_id: '99999999-9999-4999-8999-999999999999',
  email: 'dr.rivera@example.com',
  display_name: 'Dr. Rivera',
  role: 'clinician',
  patient_id: null,
};

export const TRAJECTORY_IMPROVING: Trajectory = {
  direction: 'improving',
  confidence: 0.72,
  summary: 'Balance and daily function are up. One lab is worth a look.',
  signals: [
    // Symptom domain (ADR-0034 Phase 1 capture) — makes the composite a full 3-domain
    // score so the demo/E2E card shows Symptoms + Function + Physiologic together.
    {
      code: 'symptom_pain',
      source: 'adl',
      direction: 'improving',
      detail: 'nerve pain easing over 30 days',
    },
    {
      code: 'symptom_numbness',
      source: 'adl',
      direction: 'stable',
      detail: 'numbness or tingling steady this month',
    },
    {
      code: 'biomech_balance_score',
      source: 'biomech',
      direction: 'improving',
      detail: 'balance up 8 over 30 days',
    },
    {
      code: 'adl_daily_score',
      source: 'adl',
      direction: 'stable',
      detail: 'daily function steady this month',
    },
    {
      code: '4548-4',
      source: 'lab',
      direction: 'declining',
      detail: 'long-term blood sugar slightly up',
    },
  ],
  data_gaps: ['No lab results in the last 90 days'],
  narrative_source: 'deterministic',
  // Neuropathy Status Index (ADR-0034): a full three-domain composite, improving.
  score: 74,
  score_delta_30d: 7,
  as_of: '2026-07-12',
  confidence_level: 'high',
  direction_word: 'improving',
  data_is_stale: false,
};

export const TRAJECTORY_DECLINING: Trajectory = {
  direction: 'declining',
  confidence: 0.55,
  summary: 'Balance has slipped this month. Worth a closer look with your care team.',
  signals: [
    {
      code: 'biomech_balance_score',
      source: 'biomech',
      direction: 'declining',
      detail: 'balance down 6 over 30 days',
    },
    {
      // An insufficient_data signal MUST render the "not enough data" state,
      // never a fabricated "stable" (ADR-0015 signal honesty).
      code: 'adl_daily_score',
      source: 'adl',
      direction: 'insufficient_data',
      detail: 'not enough check-ins yet to judge',
    },
  ],
  data_gaps: ['Fewer than 3 check-ins this month'],
  narrative_source: 'deterministic',
  // NSI declining: lower score, a negative 30-day delta.
  score: 61,
  score_delta_30d: -6,
  as_of: '2026-07-11',
  confidence_level: 'medium',
  direction_word: 'declining',
  data_is_stale: false,
};

export const TRAJECTORY_INSUFFICIENT: Trajectory = {
  direction: 'insufficient_data',
  confidence: 0.1,
  summary: 'There is not enough data yet to judge a trend.',
  signals: [],
  data_gaps: ['No BioMech reports yet', 'No daily check-ins yet'],
  narrative_source: 'deterministic',
  // No domain present yet — the NSI is null (the "not enough data" card).
  score: null,
  score_delta_30d: null,
  as_of: null,
  confidence_level: null,
  direction_word: null,
  data_is_stale: false,
};

/** Default observations (mirror src/test/fixtures.ts): balance (3 numeric points,
 *  higher-is-better) drives a "better" delta; HbA1c has a single reading, so
 *  selecting it shows the <2-point empty state. */
export const OBSERVATIONS: ObservationItem[] = [
  obs('biomech_balance_score', 'Balance score', 65, '{score}', '2026-07-02T10:00:00Z', 'biomech'),
  obs('biomech_balance_score', 'Balance score', 64, '{score}', '2026-06-04T10:00:00Z', 'biomech'),
  obs('biomech_balance_score', 'Balance score', 57, '{score}', '2026-05-06T10:00:00Z', 'biomech'),
  obs('biomech_sway_velocity', 'Sway velocity', 11.4, 'mm/s', '2026-07-02T10:00:00Z', 'biomech'),
  obs('biomech_sway_velocity', 'Sway velocity', 12.9, 'mm/s', '2026-06-04T10:00:00Z', 'biomech'),
  obs('4548-4', 'Hemoglobin A1c', 7.2, '%', '2026-06-20T09:00:00Z', 'lab'),
];

/** Trends showcase: exercises "better", "worse", "unit changed", and the
 *  single-reading empty state in one payload. */
export const OBSERVATIONS_TRENDS: ObservationItem[] = [
  // higher-is-better, rising → "better"
  obs('biomech_balance_score', 'Balance score', 60, '{score}', '2026-05-01T10:00:00Z', 'biomech'),
  obs('biomech_balance_score', 'Balance score', 68, '{score}', '2026-06-01T10:00:00Z', 'biomech'),
  // lower-is-better, rising → "worse"
  obs('biomech_sway_velocity', 'Sway velocity', 9, 'mm/s', '2026-05-02T10:00:00Z', 'biomech'),
  obs('biomech_sway_velocity', 'Sway velocity', 13, 'mm/s', '2026-06-02T10:00:00Z', 'biomech'),
  // two readings with DIFFERENT unit strings → "unit changed", no delta
  obs('hba1c', 'Hemoglobin A1c', 7, '%', '2026-05-03T09:00:00Z', 'lab'),
  obs('hba1c', 'Hemoglobin A1c', 53, 'mmol/mol', '2026-06-03T09:00:00Z', 'lab'),
  // single reading → chart empty state ("not enough readings")
  obs('biomech_gait_speed', 'Gait speed', 1.1, 'm/s', '2026-06-04T10:00:00Z', 'biomech'),
];

export const CAPABILITIES: CapabilityStateOut[] = [
  cap('ingest_biomech', 'BioMech report upload', true, 'patient', true),
  cap('ingest_labs', 'Lab result upload', true, 'patient', true),
  cap('ingest_adl', 'Daily function check-in', false, 'patient', true),
  // Opt-in symptom capture (ADR-0034 Phase 1) — default OFF.
  cap('ingest_symptoms', 'Symptom check-in (pain & numbness)', false, 'patient', true),
  cap('emr_connect', 'Medical record connection', true, 'patient', true),
];

/** Capabilities with the symptom-capture toggle ON — for the symptom check-in E2E. */
export const CAPABILITIES_SYMPTOMS_ON: CapabilityStateOut[] = CAPABILITIES.map((c) =>
  c.key === 'ingest_symptoms' ? { ...c, active: true } : c,
);

/** Adds one enforced=false ("coming soon") row to prove the read-only rendering. */
export const CAPABILITIES_WITH_UNWIRED: CapabilityStateOut[] = [
  ...CAPABILITIES,
  cap('future_source', 'Wearable step count', false, 'patient', false),
];

export const CONNECTION_PENDING: ConnectionOut = {
  id: '33333333-3333-4333-8333-333333333333',
  clinic_id: '44444444-4444-4444-8444-444444444444',
  clinic_name: 'Advanced Health & Wellness',
  status: 'pending',
  initiated_by: 'clinic',
  consent_granted_at: null,
  revoked_at: null,
};

export const CONNECTION_ACTIVE: ConnectionOut = {
  ...CONNECTION_PENDING,
  id: '55555555-5555-4555-8555-555555555555',
  clinic_name: 'Regional Medical Center',
  status: 'active',
  consent_granted_at: '2026-06-01T12:00:00Z',
};

// ---- EMR connect fixtures (ADR-0028; shapes mirror backend/app/schemas/emr.py) ----

export const EMR_STATE = 'synthetic-emr-state';
export const EMR_AUTH_CODE = 'synthetic-emr-auth-code';
export const EMR_CONNECTION_ID = '66666666-6666-4666-8666-666666666666';

/** Mirrors the real registry (backend/app/emr/providers.py): one entry with a public
 * sandbox (connectable) and one without (renders "Not available yet"). */
export const EMR_PROVIDERS: EmrProviderOut[] = [
  {
    key: 'epic',
    name: 'Epic (MyChart)',
    vendor: 'Epic Systems',
    sandbox_fhir_base: 'https://fhir.epic.example/api/FHIR/R4',
    note: 'Largest US hospital EMR; patient portal is MyChart.',
  },
  {
    key: 'meditech',
    name: 'MEDITECH',
    vendor: 'MEDITECH',
    sandbox_fhir_base: null,
    note: 'Community-hospital EMR; sandbox access granted on registration.',
  },
];

export const EMR_CONNECTION_ACTIVE: EmrConnectionOut = {
  id: EMR_CONNECTION_ID,
  patient_id: '22222222-2222-4222-8222-222222222222',
  fhir_base: 'https://fhir.epic.example/api/FHIR/R4',
  provider_name: 'Epic (MyChart)',
  status: 'active',
  granted_scope: 'launch/patient patient/Observation.read offline_access',
  patient_fhir_id: 'synthetic-fhir-patient-9',
  token_expires_at: '2026-07-13T13:00:00Z',
  revoked_at: null,
};

export const EMR_PULL: EmrPullOut = {
  imported: 2,
  results: [
    emrLab('4548-4', 'Hemoglobin A1c', 7.2, '%'),
    emrLab('2345-7', 'Glucose', 101, 'mg/dL'),
  ],
};

// ---- clinician fixtures ----

export const PANEL_PATIENT_ID = '22222222-2222-4222-8222-222222222222';

export const PANEL: PanelOut = {
  patients: [
    {
      patient_id: PANEL_PATIENT_ID,
      display_name: 'Pat Example',
      connection_id: '55555555-5555-4555-8555-555555555555',
      consent_granted_at: '2026-06-01T12:00:00Z',
    },
    {
      patient_id: '77777777-7777-4777-8777-777777777777',
      display_name: 'Jordan Marsh',
      connection_id: '88888888-8888-4888-8888-888888888888',
      consent_granted_at: '2026-05-20T09:00:00Z',
    },
  ],
};

export const PANEL_EMPTY: PanelOut = { patients: [] };

export const CLINIC_CAPABILITIES: CapabilityStateOut[] = [
  cap('ingest_biomech', 'BioMech report upload', true, 'clinic', true, '2026-08-06T23:59:59Z'),
  cap('ingest_labs', 'Lab result upload', true, 'clinic', true),
  cap('ingest_adl', 'Daily function check-in', false, 'clinic', true),
  cap('ai_narrative', 'AI trajectory summary', true, 'clinic', true),
  // Patient-held consent (ADR-0020 §3(b)): ALWAYS managed_by='patient', rendered
  // read-only in the clinician console.
  cap('share_with_clinic', 'Share data with my clinic', true, 'patient', true),
];

/** 25 synthetic clinic observations so the Observations tab pager spans pages,
 *  while still leaving a single-reading code so the trend table shows "not judged". */
export const CLINIC_OBSERVATIONS: ObservationItem[] = buildClinicObservations();

// ---- scenario + install ----

/** What the mock backend observed — specs assert against this (e.g. that a deletion
 *  actually reached the API, not just that the UI navigated away). */
export interface MockApiState {
  /** How many DELETE /auth/me requests succeeded (password matched -> 204). */
  accountDeletions: number;
  /** How many POST /emr/connections/{id}/pull requests were served. */
  emrPulls: number;
  /** How many DELETE /emr/connections/{id} revocations were served. */
  emrRevocations: number;
  /** Every POST /adl body the mock served (any status) — the offline-queue spec
   *  asserts the flushed entry REACHED the API with its true check_in_date. */
  adlPosts: unknown[];
  /** How many GET /me/export requests were served (ADR-0031). */
  dataExports: number;
}

/** The full ExportOut shape (ADR-0031) — mirrors backend/app/schemas/export.py, reusing
 *  the other fixtures so it stays in lockstep with what the real API would return. */
const EXPORT_OBSERVATIONS_OUT: ExportObservation[] = [
  {
    id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    source: 'lab',
    origin: 'ehr_imported',
    code: '4548-4',
    code_system: 'LOINC',
    value_num: 7.2,
    value_text: null,
    unit: '%',
    unit_system: 'UCUM',
    effective_at: '2026-06-20T09:00:00Z',
    recorded_at: '2026-06-20T09:05:00Z',
    status: 'final',
    revises_id: null,
    recorded_by_role: 'patient',
    quality: { human_confirmed: true },
    payload: { panel: 'metabolic' },
  },
];

export const EXPORT_OUT: ExportOut = {
  exported_at: '2026-07-15T10:00:00Z',
  schema_version: '1.0',
  subject_id: '22222222-2222-4222-8222-222222222222',
  account: {
    display_name: 'Pat Example',
    email: SYNTHETIC_EMAIL,
    role: 'patient',
    created_at: '2026-05-01T08:00:00Z',
  },
  patient: {
    patient_id: '22222222-2222-4222-8222-222222222222',
    display_name: 'Pat Example',
    connection_mode: 'self_connected',
    created_at: '2026-05-01T08:00:00Z',
  },
  observations: EXPORT_OBSERVATIONS_OUT,
  trajectory: TRAJECTORY_IMPROVING,
  capabilities: CAPABILITIES,
  clinic_connections: [CONNECTION_ACTIVE],
  emr_connections: [EMR_CONNECTION_ACTIVE],
};

export interface Scenario {
  me?: MeOut;
  trajectory?: Trajectory;
  observations?: ObservationItem[];
  capabilities?: CapabilityStateOut[];
  connections?: ConnectionOut[];
  /** ADL POST result (defaults to a fresh, non-superseded check-in). */
  adl?: { status?: number; body?: unknown };
  /** BioMech import result. */
  biomech?: { status?: number; body?: unknown };
  /** Override the PUT /capabilities/:key outcome (e.g. a 409 clinically-managed). */
  putCapability?: { status: number; body: unknown };
  // clinician surface
  panel?: PanelOut;
  clinicTrajectory?: Trajectory;
  clinicObservations?: ObservationItem[];
  clinicCapabilities?: CapabilityStateOut[];
}

const CLINICALLY_MANAGED_409 = {
  detail: 'Your clinic manages this source right now, so it can’t be changed here.',
};

const FEATURE_OFF_409 = {
  detail: 'This check-in is turned off right now.',
};

const JSON_HEADERS = { 'content-type': 'application/json' };

async function fulfillJson(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, headers: JSON_HEADERS, body: JSON.stringify(body) });
}

const unauthorized = (route: Route) => fulfillJson(route, 401, { detail: 'Not authenticated' });
const patientNotFound = (route: Route) => fulfillJson(route, 404, { detail: 'Patient not found' });

/**
 * Install the full API mock on a page. Only the app's own API path prefixes are
 * intercepted; the HTML/JS/CSS/font requests fall through to the real preview
 * build (so we test the REAL production bundle). `/favicon.ico` is fulfilled 204
 * so it never logs a benign 404 to the console.
 */
export async function installApiMocks(page: Page, scenario: Scenario = {}): Promise<MockApiState> {
  const state: MockApiState = {
    accountDeletions: 0,
    emrPulls: 0,
    emrRevocations: 0,
    adlPosts: [],
    dataExports: 0,
  };
  const me = scenario.me ?? ME;
  const trajectory = scenario.trajectory ?? TRAJECTORY_IMPROVING;
  const observations = scenario.observations ?? OBSERVATIONS;
  const capabilities = scenario.capabilities ?? CAPABILITIES;
  const connections = scenario.connections ?? [CONNECTION_PENDING, CONNECTION_ACTIVE];
  const panel = scenario.panel ?? PANEL;
  const clinicTrajectory = scenario.clinicTrajectory ?? TRAJECTORY_IMPROVING;
  const clinicObservations = scenario.clinicObservations ?? OBSERVATIONS;
  const clinicCapabilities = scenario.clinicCapabilities ?? CLINIC_CAPABILITIES;

  await page.route('**/favicon.ico', (route) => route.fulfill({ status: 204, body: '' }));

  await page.route(
    // /emr shares its prefix between API paths and the SPA's /emr/callback relay
    // route, exactly like /clinic (see the document-navigation note below).
    /\/(auth|me|observations|adl|biomech|trajectory|capabilities|connections|clinic|emr)(\/|$|\?)/,
    async (route) => {
      const req = route.request();
      // Only intercept the app's fetch/XHR API calls. The client routes /clinic and
      // /clinic/patients/{id} share a prefix with the API path space, so a document
      // navigation to them must render the SPA, not be answered as an API call. The
      // preview server proxies these prefixes to the (absent) dev backend, so we
      // serve the REAL built dist/index.html here; its /assets/*.js + /config.js
      // still load from the real preview build.
      const resourceType = req.resourceType();
      if (resourceType === 'document') {
        return route.fulfill({
          status: 200,
          headers: { 'content-type': 'text/html; charset=utf-8' },
          body: indexHtml(),
        });
      }
      if (resourceType !== 'fetch' && resourceType !== 'xhr') {
        return route.continue();
      }
      const method = req.method();
      const path = new URL(req.url()).pathname;

      // ---- auth (anonymous endpoints) ----
      if (method === 'POST' && path === '/auth/login') {
        const body = req.postDataJSON() as { email: string; password: string };
        if (body.email === SYNTHETIC_EMAIL && body.password === SYNTHETIC_PASSWORD) {
          return fulfillJson(route, 200, tokenBody());
        }
        return fulfillJson(route, 401, { detail: 'Invalid email or password' });
      }
      if (method === 'POST' && path === '/auth/register') {
        return fulfillJson(route, 201, tokenBody());
      }
      if (method === 'POST' && path === '/auth/refresh') {
        const body = req.postDataJSON() as { refresh_token: string };
        if (body.refresh_token === SYNTHETIC_REFRESH_TOKEN) {
          return fulfillJson(route, 200, {
            access_token: SYNTHETIC_REFRESHED_ACCESS_TOKEN,
            token_type: 'bearer',
          });
        }
        return fulfillJson(route, 401, { detail: 'Invalid token' });
      }

      // ---- everything below requires a valid bearer ----
      if (!isAuthorized(route)) {
        return unauthorized(route);
      }

      if (method === 'GET' && path === '/auth/me') {
        return fulfillJson(route, 200, me);
      }
      // Account & data deletion (ADR-0027): 204 on the right password (recorded in
      // MockApiState), 403 with the backend's verbatim detail otherwise.
      if (method === 'DELETE' && path === '/auth/me') {
        const body = req.postDataJSON() as { password: string };
        if (body.password === SYNTHETIC_PASSWORD) {
          state.accountDeletions += 1;
          return route.fulfill({ status: 204, body: '' });
        }
        return fulfillJson(route, 403, { detail: DELETE_WRONG_PASSWORD_DETAIL });
      }
      // Data export (ADR-0031): the complete record for the signed-in patient. The
      // full ExportOut shape, so the browser exercises exactly what the real API sends.
      if (method === 'GET' && path === '/me/export') {
        state.dataExports += 1;
        return fulfillJson(route, 200, EXPORT_OUT);
      }
      if (method === 'GET' && path === '/trajectory') {
        return fulfillJson(route, 200, trajectory);
      }
      if (method === 'GET' && path === '/observations') {
        return fulfillJson(route, 200, page_(observations, req.url()));
      }
      if (method === 'POST' && path === '/adl') {
        const body = req.postDataJSON() as {
          walking: number;
          stairs: number;
          balance_confidence: number;
        };
        state.adlPosts.push(body);
        // An error status (feature-off 409, etc.) returns the raw override body —
        // that IS the real error shape. A success status instead MERGES the override
        // onto the full AdlCheckInOut default, so a { status: 200, body: { superseded:
        // true } } scenario flips one field without dropping the required check_in_date
        // / daily_score — a partial 200 body would be a fiction the real API (Pydantic
        // AdlCheckInOut, all fields required) could never return.
        const adlStatus = scenario.adl?.status ?? 200;
        if (adlStatus >= 400) {
          return fulfillJson(route, adlStatus, scenario.adl?.body ?? FEATURE_OFF_409);
        }
        return fulfillJson(route, adlStatus, {
          check_in_date: '2026-07-13',
          daily_score: body.walking + body.stairs + body.balance_confidence,
          superseded: false,
          ...(typeof scenario.adl?.body === 'object' ? scenario.adl.body : {}),
        });
      }
      if (method === 'POST' && path === '/biomech/reports') {
        if (scenario.biomech?.status !== undefined) {
          return fulfillJson(route, scenario.biomech.status, scenario.biomech.body);
        }
        return fulfillJson(route, 200, {
          report_kind: 'balance',
          assessment_at: '2026-07-02T10:00:00Z',
          imported: 3,
          skipped: 0,
          warnings: [],
          ...(typeof scenario.biomech?.body === 'object' ? scenario.biomech.body : {}),
        });
      }
      if (method === 'GET' && path === '/capabilities') {
        return fulfillJson(route, 200, { capabilities });
      }
      if (method === 'PUT' && /^\/capabilities\/[^/]+$/.test(path)) {
        if (scenario.putCapability !== undefined) {
          return fulfillJson(route, scenario.putCapability.status, scenario.putCapability.body);
        }
        const key = decodeURIComponent(path.split('/')[2] ?? '');
        const body = req.postDataJSON() as { active: boolean };
        const existing = capabilities.find((row) => row.key === key);
        if (existing === undefined) {
          return fulfillJson(route, 404, { detail: 'Unknown capability' });
        }
        return fulfillJson(route, 200, { ...existing, active: body.active });
      }
      if (method === 'GET' && path === '/connections') {
        return fulfillJson(route, 200, connections);
      }
      if (method === 'POST' && /^\/connections\/[^/]+\/consent$/.test(path)) {
        return fulfillJson(route, 200, {
          ...CONNECTION_PENDING,
          status: 'active',
          consent_granted_at: '2026-07-13T12:00:00Z',
        });
      }
      if (method === 'DELETE' && /^\/connections\/[^/]+$/.test(path)) {
        return route.fulfill({ status: 204, body: '' });
      }

      // ---- EMR connect (ADR-0028; mirrors backend/app/api/routes/emr.py) ----
      if (method === 'GET' && path === '/emr/providers') {
        // The real endpoint's search: case-insensitive match on key, name, or vendor.
        const q = (new URL(req.url()).searchParams.get('q') ?? '').trim().toLowerCase();
        return fulfillJson(
          route,
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
        // The authorize URL points back at the app's OWN /emr/callback with the
        // code+state the real EMR would append — simulating the OAuth round trip
        // without leaving the origin (the /emr document navigation renders the SPA).
        const origin = new URL(req.url()).origin;
        return fulfillJson(route, 200, {
          connection_id: EMR_CONNECTION_ID,
          authorize_url: `${origin}/emr/callback?code=${EMR_AUTH_CODE}&state=${EMR_STATE}`,
          state: EMR_STATE,
        });
      }
      if (method === 'GET' && path === '/emr/callback') {
        const params = new URL(req.url()).searchParams;
        if (params.get('state') !== EMR_STATE || params.get('code') !== EMR_AUTH_CODE) {
          // Single-use/unknown state — the real endpoint's 404.
          return fulfillJson(route, 404, { detail: 'Unknown, expired, or already-used state' });
        }
        return fulfillJson(route, 200, EMR_CONNECTION_ACTIVE);
      }
      if (method === 'POST' && /^\/emr\/connections\/[^/]+\/pull$/.test(path)) {
        state.emrPulls += 1;
        return fulfillJson(route, 200, EMR_PULL);
      }
      if (method === 'DELETE' && /^\/emr\/connections\/[^/]+$/.test(path)) {
        state.emrRevocations += 1;
        // The real revoke returns the connection with status=revoked (200, not 204).
        return fulfillJson(route, 200, {
          ...EMR_CONNECTION_ACTIVE,
          status: 'revoked',
          granted_scope: null,
          revoked_at: '2026-07-13T14:00:00Z',
        });
      }

      // ---- clinician surface ----
      if (method === 'POST' && path === '/clinic/invitations') {
        return fulfillJson(route, 202, {
          detail: 'If this email belongs to a patient account, an invitation is now pending.',
        });
      }
      if (method === 'GET' && path === '/clinic/patients') {
        return fulfillJson(route, 200, panel);
      }
      const patientMatch =
        /^\/clinic\/patients\/([^/]+)\/(trajectory|observations|capabilities)$/.exec(path);
      if (method === 'GET' && patientMatch) {
        const id = decodeURIComponent(patientMatch[1] ?? '');
        const kind = patientMatch[2];
        if (id !== PANEL_PATIENT_ID) {
          return patientNotFound(route);
        }
        if (kind === 'trajectory') {
          return fulfillJson(route, 200, clinicTrajectory);
        }
        if (kind === 'observations') {
          return fulfillJson(route, 200, page_(clinicObservations, req.url()));
        }
        return fulfillJson(route, 200, { capabilities: clinicCapabilities });
      }
      const putCapMatch = /^\/clinic\/patients\/([^/]+)\/capabilities\/([^/]+)$/.exec(path);
      if (method === 'PUT' && putCapMatch) {
        const id = decodeURIComponent(putCapMatch[1] ?? '');
        const key = decodeURIComponent(putCapMatch[2] ?? '');
        const body = req.postDataJSON() as { active: boolean; expires_at?: string | null };
        if (!body.active && body.expires_at != null) {
          return fulfillJson(route, 422, {
            detail: [
              {
                type: 'value_error',
                loc: ['body'],
                msg: 'Value error, expires_at only applies when active=true; omit it when disabling',
              },
            ],
          });
        }
        if (id !== PANEL_PATIENT_ID) {
          return patientNotFound(route);
        }
        const existing = clinicCapabilities.find((row) => row.key === key);
        if (existing === undefined) {
          return fulfillJson(route, 404, { detail: 'Unknown capability' });
        }
        return fulfillJson(route, 200, {
          ...existing,
          active: body.active,
          expires_at: body.expires_at ?? null,
        });
      }

      // Any unmocked API path is a test bug — fail loudly rather than hang.
      return fulfillJson(route, 500, { detail: `Unmocked ${method} ${path}` });
    },
  );
  return state;
}

export { CLINICALLY_MANAGED_409, FEATURE_OFF_409 };

// ---- helpers ----

/** The real built index.html, read once (the preview build produces it). */
let cachedIndexHtml: string | null = null;
function indexHtml(): string {
  if (cachedIndexHtml === null) {
    const here = dirname(fileURLToPath(import.meta.url));
    cachedIndexHtml = readFileSync(join(here, '..', '..', 'dist', 'index.html'), 'utf8');
  }
  return cachedIndexHtml;
}

function tokenBody() {
  return {
    access_token: SYNTHETIC_ACCESS_TOKEN,
    refresh_token: SYNTHETIC_REFRESH_TOKEN,
    token_type: 'bearer',
  };
}

/** Slice an observation array into an ObservationPage honoring limit/offset. */
function page_(items: ObservationItem[], url: string) {
  const params = new URL(url).searchParams;
  const limit = Number(params.get('limit') ?? '100');
  const offset = Number(params.get('offset') ?? '0');
  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    limit,
    offset,
  };
}

function emrLab(loinc_code: string, display: string, value: number, unit: string) {
  return {
    loinc_code,
    source_record_id: `synthetic-${loinc_code}`,
    display,
    value,
    value_text: null,
    unit,
    effective_at: '2026-06-15T08:30:00Z',
    issued_at: null,
    status: 'final',
    reference_range: null,
    interpretation: null,
    code_system: 'LOINC',
    unit_system: 'UCUM',
  };
}

function obs(
  code: string,
  display: string,
  value: number,
  unit: string,
  effective_at: string,
  source: string,
): ObservationItem {
  return { code, display, value, value_text: null, unit, effective_at, source, status: 'final' };
}

function cap(
  key: string,
  name: string,
  active: boolean,
  managed_by: 'patient' | 'clinic',
  enforced: boolean,
  expires_at: string | null = null,
): CapabilityStateOut {
  return { key, name, active, managed_by, expires_at, enforced };
}

function buildClinicObservations(): ObservationItem[] {
  const items: ObservationItem[] = [];
  for (let i = 0; i < 12; i += 1) {
    const day = String(28 - i).padStart(2, '0');
    items.push(
      obs(
        'biomech_balance_score',
        'Balance score',
        60 + i,
        '{score}',
        `2026-06-${day}T10:00:00Z`,
        'biomech',
      ),
    );
  }
  for (let i = 0; i < 12; i += 1) {
    const day = String(28 - i).padStart(2, '0');
    items.push(
      obs(
        'biomech_sway_velocity',
        'Sway velocity',
        10 + i * 0.2,
        'mm/s',
        `2026-05-${day}T10:00:00Z`,
        'biomech',
      ),
    );
  }
  // A single-reading lab so the trend table shows "not judged".
  items.push(obs('4548-4', 'Hemoglobin A1c', 7.1, '%', '2026-04-10T09:00:00Z', 'lab'));
  return items;
}
