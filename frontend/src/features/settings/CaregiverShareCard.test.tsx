/**
 * "Share with a loved one" (ADR-0047): invite-code generation (shown once, expiry
 * stated), open-invite cancel, the double opt-in accept/decline, scope change, and
 * the instant two-tap revoke — the patient controls everything.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import {
  CAREGIVER_LINK_ACTIVE,
  CAREGIVER_LINK_PENDING,
  TEST_CAREGIVER_CODE,
} from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('CaregiverShareCard — invite codes', () => {
  it('creates an invite and shows the one-time code with its expiry', async () => {
    const user = userEvent.setup();
    renderApp('/settings');
    await user.click(await screen.findByRole('button', { name: 'Create an invite code' }));
    const code = await screen.findByText(TEST_CAREGIVER_CODE);
    expect(code).toBeInTheDocument();
    // Expiry and the shown-once honesty ride WITH the code, in the same notice
    // (scoped: the open-invites list below also mentions the expiry date).
    const notice = code.closest('[role="status"]');
    expect(notice).not.toBeNull();
    expect(notice).toHaveTextContent(/expires Jul 22, 2026/);
    expect(notice).toHaveTextContent(/won't be shown again/);
  });

  it('lists open invites (no code — it is unrecoverable) and cancels one', async () => {
    let cancelled = false;
    server.use(
      http.get('/me/caregiver-invites', () =>
        HttpResponse.json(
          cancelled
            ? []
            : [
                {
                  id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
                  created_at: '2026-07-15T10:00:00Z',
                  expires_at: '2026-07-22T10:00:00Z',
                },
              ],
        ),
      ),
      http.delete('/me/caregiver-invites/:inviteId', () => {
        cancelled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    expect(await screen.findByText('Open invites')).toBeInTheDocument();
    expect(screen.getByText(/Created Jul 15, 2026 · expires Jul 22, 2026/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => {
      expect(screen.queryByText('Open invites')).not.toBeInTheDocument();
    });
    expect(cancelled).toBe(true);
  });
});

describe('CaregiverShareCard — double opt-in and control', () => {
  it('shows a pending request by name and accepts it (only then is anything shared)', async () => {
    let accepted = false;
    server.use(
      http.get('/me/caregivers', () =>
        HttpResponse.json(
          accepted
            ? [{ ...CAREGIVER_LINK_PENDING, status: 'active', accepted_at: '2026-07-15T12:00:00Z' }]
            : [CAREGIVER_LINK_PENDING],
        ),
      ),
      http.post('/me/caregivers/:linkId/accept', () => {
        accepted = true;
        return HttpResponse.json({
          ...CAREGIVER_LINK_PENDING,
          status: 'active',
          accepted_at: '2026-07-15T12:00:00Z',
        });
      }),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    expect(await screen.findByText('Waiting for your OK')).toBeInTheDocument();
    // Nothing-shared-until-yes framing rides with the request.
    expect(screen.getByText(/Nothing is shared until you say yes/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Yes, share with Casey Example' }));
    // The reloaded list shows the now-active caregiver with the default trends scope.
    expect(await screen.findByText('Sharing with')).toBeInTheDocument();
    expect(screen.getByText('Can see their trend only')).toBeInTheDocument();
    expect(accepted).toBe(true);
  });

  it('declines a pending request', async () => {
    let declined = false;
    server.use(
      http.get('/me/caregivers', () => HttpResponse.json(declined ? [] : [CAREGIVER_LINK_PENDING])),
      http.post('/me/caregivers/:linkId/decline', () => {
        declined = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    await screen.findByText('Waiting for your OK');
    await user.click(screen.getByRole('button', { name: 'No, decline' }));
    await waitFor(() => {
      expect(screen.queryByText('Waiting for your OK')).not.toBeInTheDocument();
    });
    expect(declined).toBe(true);
  });

  it('changes an active caregiver’s scope in plain words', async () => {
    let scope = 'trends';
    server.use(
      http.get('/me/caregivers', () => HttpResponse.json([{ ...CAREGIVER_LINK_ACTIVE, scope }])),
      http.patch('/me/caregivers/:linkId', async ({ request }) => {
        const body = (await request.json()) as { scope: string };
        scope = body.scope;
        return HttpResponse.json({ ...CAREGIVER_LINK_ACTIVE, scope });
      }),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    expect(await screen.findByText('Can see their trend only')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Also share your visit summary' }));
    expect(
      await screen.findByText('Can see their trend and your visit summary'),
    ).toBeInTheDocument();
    expect(scope).toBe('full');
    // And back down again.
    await user.click(screen.getByRole('button', { name: 'Limit to trend only' }));
    expect(await screen.findByText('Can see their trend only')).toBeInTheDocument();
    expect(scope).toBe('trends');
  });

  it('revokes only after the confirm tap, then the caregiver is gone', async () => {
    let revoked = false;
    server.use(
      http.get('/me/caregivers', () => HttpResponse.json(revoked ? [] : [CAREGIVER_LINK_ACTIVE])),
      http.delete('/me/caregivers/:linkId', () => {
        revoked = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    await screen.findByText('Sharing with');
    await user.click(screen.getByRole('button', { name: 'Stop sharing' }));
    // First tap arms the confirm — nothing is revoked yet.
    expect(revoked).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Tap again to confirm' }));
    await waitFor(() => {
      expect(screen.queryByText('Sharing with')).not.toBeInTheDocument();
    });
    expect(revoked).toBe(true);
  });

  it('says plainly that sharing is not live monitoring or an emergency channel', async () => {
    renderApp('/settings');
    expect(
      await screen.findByText(/not live monitoring, and it is not for emergencies/),
    ).toBeInTheDocument();
  });
});
