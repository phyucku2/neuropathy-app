/**
 * The medication & event capture endpoints (ADR-0045 P2). Each fn hits the right method/path
 * and MINTS a `client_entry_id` (uuid) into the body — the idempotency key the caller never
 * supplies. The other routes are exercised via their feature tests; these lock the new contract.
 */

import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { storeSession } from '../auth/tokenStore';
import { TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN } from '../test/fixtures';
import { server } from '../test/server';
import {
  deregisterCaregiverPushToken,
  getEvents,
  getMedications,
  postEvent,
  postMedication,
  postMedicationChange,
  registerCaregiverPushToken,
} from './endpoints';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function signIn(): void {
  storeSession({ access_token: TEST_ACCESS_TOKEN, refresh_token: TEST_REFRESH_TOKEN });
}

describe('medication & event endpoints', () => {
  it('postMedication POSTs /medications and mints a client_entry_id', async () => {
    signIn();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('/medications', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            medication_id: 'med:abc',
            change_type: 'added',
            effective_at: '2026-07-10T00:00:00Z',
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const out = await postMedication({
      name: 'Aspirin',
      kind: 'otc',
      dose_amount: 81,
      dose_unit: 'mg',
      dose_text: null,
      prescriber: null,
      reason: null,
      started_on: '2026-07-10',
    });
    expect(out.medication_id).toBe('med:abc');
    expect(captured).not.toBeNull();
    expect((captured as unknown as { name: string }).name).toBe('Aspirin');
    expect((captured as unknown as { client_entry_id: string }).client_entry_id).toMatch(UUID_RE);
  });

  it('postMedicationChange POSTs /medications/{id}/changes with a minted client_entry_id', async () => {
    signIn();
    let capturedPath: string | null = null;
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('/medications/:id/changes', async ({ request, params }) => {
        capturedPath = String(params['id']);
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            medication_id: String(params['id']),
            change_type: 'stopped',
            effective_at: '2026-07-10T00:00:00Z',
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const out = await postMedicationChange('med:xyz', {
      change_type: 'stopped',
      dose_amount: null,
      dose_unit: null,
      dose_text: null,
      reason: null,
      effective_date: '2026-07-10',
    });
    expect(out.change_type).toBe('stopped');
    expect(capturedPath).toBe('med:xyz');
    expect((captured as unknown as { client_entry_id: string }).client_entry_id).toMatch(UUID_RE);
  });

  it('postEvent POSTs /events and mints a client_entry_id', async () => {
    signIn();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('/events', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            event_id: 'e1',
            type: 'fall',
            effective_at: '2026-07-10T00:00:00Z',
            note: null,
            reviewed: false,
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const out = await postEvent({ type: 'fall', effective_date: '2026-07-10', note: null });
    expect(out.type).toBe('fall');
    expect((captured as unknown as { type: string }).type).toBe('fall');
    expect((captured as unknown as { client_entry_id: string }).client_entry_id).toMatch(UUID_RE);
  });

  it('getMedications and getEvents GET their list paths', async () => {
    signIn();
    const meds = await getMedications();
    expect(meds.items.length).toBeGreaterThan(0);
    const events = await getEvents();
    expect(events.items.length).toBeGreaterThan(0);
  });
});

describe('caregiver push-token endpoints (ADR-0047 B2)', () => {
  it('registerCaregiverPushToken POSTs /caregiver/push-tokens with {token, platform}', async () => {
    signIn();
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('/caregiver/push-tokens', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: '11111111-1111-4111-8111-111111111111',
            platform: 'android',
            last_seen_at: '2026-07-22T00:00:00Z',
            created_at: '2026-07-22T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );
    const out = await registerCaregiverPushToken('fcm-token-xyz', 'android');
    expect(out.platform).toBe('android');
    expect(captured).toEqual({ token: 'fcm-token-xyz', platform: 'android' });
  });

  it('deregisterCaregiverPushToken DELETEs /caregiver/push-tokens with {token} (204)', async () => {
    signIn();
    let capturedMethod: string | null = null;
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.delete('/caregiver/push-tokens', async ({ request }) => {
        capturedMethod = request.method;
        captured = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await expect(deregisterCaregiverPushToken('fcm-token-xyz')).resolves.toBeUndefined();
    expect(capturedMethod).toBe('DELETE');
    expect(captured).toEqual({ token: 'fcm-token-xyz' });
  });
});
