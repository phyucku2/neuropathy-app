/** msw request handlers — the mocked API every component test runs against. */

import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import type { AdlCheckInIn, CapabilitySetIn } from '../api/types';
import {
  CAPABILITIES,
  CONNECTION_ACTIVE,
  CONNECTION_PENDING,
  ME,
  OBSERVATIONS,
  TEST_ACCESS_TOKEN,
  TEST_EMAIL,
  TEST_PASSWORD,
  TEST_REFRESH_TOKEN,
  TEST_REFRESHED_ACCESS_TOKEN,
  TRAJECTORY_IMPROVING,
} from './fixtures';

function isAuthorized(request: Request): boolean {
  const header = request.headers.get('authorization');
  return (
    header === `Bearer ${TEST_ACCESS_TOKEN}` || header === `Bearer ${TEST_REFRESHED_ACCESS_TOKEN}`
  );
}

const unauthorized = () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 });

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
];

export const server = setupServer(...handlers);
