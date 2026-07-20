/** msw request handlers — the mocked API every component test runs against. */

import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import type { AdlCheckInIn, CapabilitySetIn, ClinicianCapabilitySetIn } from '../api/types';
import {
  CAPABILITIES,
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
  EVENTS,
  EXPORT,
  ME,
  MEDICATIONS,
  OBSERVATIONS,
  PANEL,
  PANEL_PATIENT_ID,
  TEST_ACCESS_TOKEN,
  TEST_EMAIL,
  TEST_PASSWORD,
  TEST_REFRESH_TOKEN,
  TEST_REFRESHED_ACCESS_TOKEN,
  TRAJECTORY_IMPROVING,
  visitSummaryForWindow,
} from './fixtures';

export function isAuthorized(request: Request): boolean {
  const header = request.headers.get('authorization');
  return (
    header === `Bearer ${TEST_ACCESS_TOKEN}` || header === `Bearer ${TEST_REFRESHED_ACCESS_TOKEN}`
  );
}

const unauthorized = () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 });

/** 404-over-403: unknown AND unconsented ids are indistinguishable (ADR-0012). */
const patientNotFound = () => HttpResponse.json({ detail: 'Patient not found' }, { status: 404 });

/** The backend's 422 shape for the expiry-only-with-enable rule (ADR-0013). */
const expiryRefused = () =>
  HttpResponse.json(
    {
      detail: [
        {
          type: 'value_error',
          loc: ['body'],
          msg: 'Value error, expires_at only applies when active=true; omit it when disabling',
        },
      ],
    },
    { status: 422 },
  );

export const handlers = [
  http.post('/auth/login', async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.email === TEST_EMAIL && body.password === TEST_PASSWORD) {
      return HttpResponse.json({
        access_token: TEST_ACCESS_TOKEN,
        refresh_token: TEST_REFRESH_TOKEN,
        token_type: 'bearer',
      });
    }
    return HttpResponse.json({ detail: 'Invalid email or password' }, { status: 401 });
  }),

  http.post('/auth/register', () =>
    HttpResponse.json(
      {
        access_token: TEST_ACCESS_TOKEN,
        refresh_token: TEST_REFRESH_TOKEN,
        token_type: 'bearer',
      },
      { status: 201 },
    ),
  ),

  http.post('/auth/refresh', async ({ request }) => {
    const body = (await request.json()) as { refresh_token: string };
    if (body.refresh_token === TEST_REFRESH_TOKEN) {
      return HttpResponse.json({
        access_token: TEST_REFRESHED_ACCESS_TOKEN,
        token_type: 'bearer',
      });
    }
    return HttpResponse.json({ detail: 'Invalid token' }, { status: 401 });
  }),

  http.get('/auth/me', ({ request }) =>
    isAuthorized(request) ? HttpResponse.json(ME) : unauthorized(),
  ),

  // Account & data deletion (ADR-0027): 204 on the right password, 403 with the
  // backend's verbatim detail otherwise (nothing is deleted then).
  http.delete('/auth/me', async ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as { password: string };
    if (body.password === TEST_PASSWORD) {
      return new HttpResponse(null, { status: 204 });
    }
    return HttpResponse.json({ detail: DELETE_WRONG_PASSWORD_DETAIL }, { status: 403 });
  }),

  // Data export (ADR-0031): the complete record for the signed-in patient.
  http.get('/me/export', ({ request }) =>
    isAuthorized(request) ? HttpResponse.json(EXPORT) : unauthorized(),
  ),

  // Visit-Ready Summary (ADR-0045): the patient-held handout over a selectable window. The
  // mock echoes window_days and computes lead_section exactly like the backend so the picker
  // changes the payload; Cache-Control: no-store mirrors the real PHI response.
  http.get('/me/visit-summary', ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const window = Number(new URL(request.url).searchParams.get('window') ?? '60');
    return HttpResponse.json(visitSummaryForWindow(window), {
      headers: { 'Cache-Control': 'no-store' },
    });
  }),

  http.get('/trajectory', ({ request }) =>
    isAuthorized(request) ? HttpResponse.json(TRAJECTORY_IMPROVING) : unauthorized(),
  ),

  http.get('/observations', ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    return HttpResponse.json({
      items: OBSERVATIONS,
      total: OBSERVATIONS.length,
      limit: 100,
      offset: 0,
    });
  }),

  http.post('/adl', async ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as AdlCheckInIn;
    return HttpResponse.json({
      check_in_date: '2026-07-13',
      daily_score: body.walking + body.stairs + body.balance_confidence,
      superseded: false,
    });
  }),

  http.post('/biomech/reports', ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    return HttpResponse.json({
      report_kind: 'balance',
      assessment_at: '2026-07-02T10:00:00Z',
      imported: 3,
      skipped: 0,
      warnings: [],
    });
  }),

  // Medications & supplements (ADR-0045 P2): the folded list read + the append-only writes.
  // Reads mirror the real PHI response (Cache-Control: no-store).
  http.get('/medications', ({ request }) =>
    isAuthorized(request)
      ? HttpResponse.json(MEDICATIONS, { headers: { 'Cache-Control': 'no-store' } })
      : unauthorized(),
  ),

  http.post('/medications', async ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as { started_on: string };
    return HttpResponse.json(
      {
        medication_id: 'med:99999999-9999-4999-8999-999999999999',
        change_type: 'added',
        effective_at: `${body.started_on}T00:00:00Z`,
        skipped: false,
      },
      { status: 201 },
    );
  }),

  http.post('/medications/:medicationId/changes', async ({ request, params }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as { change_type: string; effective_date: string };
    return HttpResponse.json(
      {
        medication_id: String(params['medicationId']),
        change_type: body.change_type,
        effective_at: `${body.effective_date}T00:00:00Z`,
        skipped: false,
      },
      { status: 201 },
    );
  }),

  // Between-visit events & notes (ADR-0045 P2): newest-first list + append-only record.
  http.get('/events', ({ request }) =>
    isAuthorized(request)
      ? HttpResponse.json(EVENTS, { headers: { 'Cache-Control': 'no-store' } })
      : unauthorized(),
  ),

  http.post('/events', async ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as {
      type: string;
      effective_date: string;
      note: string | null;
    };
    return HttpResponse.json(
      {
        event_id: 'aaaaaaaa-0000-4000-8000-0000000000ff',
        type: body.type,
        effective_at: `${body.effective_date}T00:00:00Z`,
        note: body.note,
        reviewed: false,
        skipped: false,
      },
      { status: 201 },
    );
  }),

  http.get('/capabilities', ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    return HttpResponse.json({ capabilities: CAPABILITIES });
  }),

  http.put('/capabilities/:key', async ({ request, params }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as CapabilitySetIn;
    const existing = CAPABILITIES.find((row) => row.key === params['key']);
    if (existing === undefined) {
      return HttpResponse.json({ detail: 'Unknown capability' }, { status: 404 });
    }
    return HttpResponse.json({ ...existing, active: body.active });
  }),

  http.get('/connections', ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    return HttpResponse.json([CONNECTION_PENDING, CONNECTION_ACTIVE]);
  }),

  http.post('/connections/:id/consent', ({ request }) =>
    isAuthorized(request)
      ? HttpResponse.json({
          ...CONNECTION_PENDING,
          status: 'active',
          consent_granted_at: '2026-07-13T12:00:00Z',
        })
      : unauthorized(),
  ),

  http.delete('/connections/:id', ({ request }) =>
    isAuthorized(request) ? new HttpResponse(null, { status: 204 }) : unauthorized(),
  ),

  // ---- EMR connect (ADR-0028; mirrors backend/app/api/routes/emr.py) ----

  http.get('/emr/providers', ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    // The real endpoint's search: case-insensitive match on key, name, or vendor.
    const q = (new URL(request.url).searchParams.get('q') ?? '').trim().toLowerCase();
    return HttpResponse.json(
      EMR_PROVIDERS.filter(
        (p) =>
          q === '' ||
          p.key.toLowerCase().includes(q) ||
          p.name.toLowerCase().includes(q) ||
          p.vendor.toLowerCase().includes(q),
      ),
    );
  }),

  http.post('/emr/connect', async ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as { provider_key?: string | null };
    if (body.provider_key === 'meditech') {
      // The real 422 for a registry provider with no public sandbox.
      return HttpResponse.json(
        { detail: 'Provider has no public sandbox; supply fhir_base explicitly' },
        { status: 422 },
      );
    }
    return HttpResponse.json(EMR_CONNECT_START);
  }),

  http.get('/emr/callback', ({ request }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const url = new URL(request.url);
    if (
      url.searchParams.get('state') !== EMR_STATE ||
      url.searchParams.get('code') !== EMR_AUTH_CODE
    ) {
      // Single-use/unknown state — the real endpoint's 404.
      return HttpResponse.json(
        { detail: 'Unknown, expired, or already-used state' },
        { status: 404 },
      );
    }
    return HttpResponse.json(EMR_CONNECTION_ACTIVE);
  }),

  http.post('/emr/connections/:id/pull', ({ request }) =>
    isAuthorized(request) ? HttpResponse.json(EMR_PULL) : unauthorized(),
  ),

  http.delete('/emr/connections/:id', ({ request }) =>
    isAuthorized(request) ? HttpResponse.json(EMR_CONNECTION_REVOKED) : unauthorized(),
  ),

  // ---- clinician surface ----

  http.post('/clinic/invitations', ({ request }) =>
    isAuthorized(request)
      ? // Byte-identical 202 whether or not the email matched (non-enumeration).
        HttpResponse.json(
          { detail: 'If this email belongs to a patient account, an invitation is now pending.' },
          { status: 202 },
        )
      : unauthorized(),
  ),

  http.get('/clinic/patients', ({ request }) =>
    isAuthorized(request) ? HttpResponse.json(PANEL) : unauthorized(),
  ),

  http.get('/clinic/patients/:patientId/trajectory', ({ request, params }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    return params['patientId'] === PANEL_PATIENT_ID
      ? HttpResponse.json(TRAJECTORY_IMPROVING)
      : patientNotFound();
  }),

  // Clinician-side Visit-Ready Summary (ADR-0045): SAME shape/data as the patient print,
  // behind the consented-connection gate → non-enumerating 404 for any other id.
  http.get('/clinic/patients/:patientId/visit-summary', ({ request, params }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    if (params['patientId'] !== PANEL_PATIENT_ID) {
      return patientNotFound();
    }
    const window = Number(new URL(request.url).searchParams.get('window') ?? '60');
    return HttpResponse.json(visitSummaryForWindow(window), {
      headers: { 'Cache-Control': 'no-store' },
    });
  }),

  http.get('/clinic/patients/:patientId/observations', ({ request, params }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    if (params['patientId'] !== PANEL_PATIENT_ID) {
      return patientNotFound();
    }
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get('limit') ?? '50');
    const offset = Number(url.searchParams.get('offset') ?? '0');
    return HttpResponse.json({
      items: OBSERVATIONS.slice(offset, offset + limit),
      total: OBSERVATIONS.length,
      limit,
      offset,
    });
  }),

  http.get('/clinic/patients/:patientId/capabilities', ({ request, params }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    return params['patientId'] === PANEL_PATIENT_ID
      ? HttpResponse.json({ capabilities: CLINIC_CAPABILITIES })
      : patientNotFound();
  }),

  http.put('/clinic/patients/:patientId/capabilities/:key', async ({ request, params }) => {
    if (!isAuthorized(request)) {
      return unauthorized();
    }
    const body = (await request.json()) as ClinicianCapabilitySetIn;
    // Schema validation runs before the existence gate in FastAPI.
    if (!body.active && body.expires_at != null) {
      return expiryRefused();
    }
    if (params['patientId'] !== PANEL_PATIENT_ID) {
      return patientNotFound();
    }
    const existing = CLINIC_CAPABILITIES.find((row) => row.key === params['key']);
    if (existing === undefined) {
      return HttpResponse.json({ detail: 'Unknown capability' }, { status: 404 });
    }
    return HttpResponse.json({
      ...existing,
      active: body.active,
      expires_at: body.expires_at ?? null,
    });
  }),
];

export const server = setupServer(...handlers);

/** Make GET /auth/me answer with the clinician account for the current test. */
export function actAsClinician(): void {
  server.use(
    http.get('/auth/me', ({ request }) =>
      isAuthorized(request) ? HttpResponse.json(CLINICIAN_ME) : unauthorized(),
    ),
  );
}
