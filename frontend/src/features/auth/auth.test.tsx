import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';
import type { AdlCheckInIn } from '../../api/types';
import { enqueueCheckIn, listQueuedCheckIns } from '../../features/checkin/offlineQueue';
import { ME, TEST_EMAIL, TEST_PASSWORD, TEST_REFRESH_TOKEN } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

const REFRESH_TOKEN_KEY = 'neuropathy.refresh_token';
const QUEUED = { walking: 1, stairs: 2, balance_confidence: 3, check_in_date: '2026-07-01' };

beforeEach(() => {
  localStorage.clear();
});

describe('auth screens', () => {
  it('redirects anonymous visitors to the login screen', async () => {
    renderApp('/', { authenticated: false });
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('signs in and lands on the trajectory home screen', async () => {
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Improving')).toBeInTheDocument();
  });

  it('shows a friendly error for a wrong password', async () => {
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), 'not-the-one');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "That email or password didn't match",
    );
  });

  it('surfaces other login failures with the server detail', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({ detail: 'Account locked' }, { status: 423 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Account locked');
  });

  it('registers a new account and lands home', async () => {
    const user = userEvent.setup();
    renderApp('/register', { authenticated: false });
    await user.type(screen.getByLabelText('Your name'), 'Pat Example');
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Improving')).toBeInTheDocument();
  });

  it('rejects a too-short password before calling the API', async () => {
    const user = userEvent.setup();
    renderApp('/register', { authenticated: false });
    const passwordField = screen.getByLabelText('Password');
    passwordField.removeAttribute('minlength'); // bypass native validation to test ours
    await user.type(screen.getByLabelText('Your name'), 'Pat Example');
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(passwordField, 'short');
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('at least 8 characters');
  });

  it('shows the register error detail from the server', async () => {
    server.use(
      http.post('/auth/register', () =>
        HttpResponse.json({ detail: 'Email already registered' }, { status: 409 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/register', { authenticated: false });
    await user.type(screen.getByLabelText('Your name'), 'Pat Example');
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Email already registered');
  });

  it('clears the stored session when the post-login profile read fails', async () => {
    server.use(
      http.get('/auth/me', () =>
        HttpResponse.json({ detail: 'Profile unavailable' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Profile unavailable');
    // The failed sign-in must not leave a live refresh token behind (kiosk risk).
    expect(sessionStorage.getItem('neuropathy.refresh_token')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('an OFFLINE boot never wipes the offline queue or the stored refresh token (repro: transient failure is not a session end)', async () => {
    // A check-in was captured offline; the tab closed; the app is reopened
    // while STILL offline — the restore GET /auth/me network-fails.
    enqueueCheckIn(ME.user_id, QUEUED);
    sessionStorage.setItem(REFRESH_TOKEN_KEY, TEST_REFRESH_TOKEN);
    server.use(http.get('/auth/me', () => HttpResponse.error()));

    const { unmount } = renderApp('/', { authenticated: false });

    // The UI lands on login (nothing renders authenticated without a profile)...
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    // ...but the captured health answers AND the refresh token both survive:
    // being offline must not destroy the very data the queue exists to protect.
    expect(listQueuedCheckIns(ME.user_id)).toHaveLength(1);
    expect(sessionStorage.getItem(REFRESH_TOKEN_KEY)).toBe(TEST_REFRESH_TOKEN);
    unmount();

    // A LATER boot with connectivity: the stored token restores the session
    // (401 → refresh → retry) and the queued entry flushes automatically.
    server.resetHandlers();
    const bodies: AdlCheckInIn[] = [];
    server.use(
      http.post('/adl', async ({ request }) => {
        const body = (await request.json()) as AdlCheckInIn;
        bodies.push(body);
        return HttpResponse.json({
          check_in_date: body.check_in_date,
          daily_score: 6,
          superseded: false,
        });
      }),
    );
    renderApp('/', { authenticated: false }); // the surviving token drives the restore
    expect(await screen.findByText('Improving')).toBeInTheDocument();
    await waitFor(() => {
      expect(bodies.map((b) => b.check_in_date)).toEqual(['2026-07-01']);
    });
    expect(listQueuedCheckIns(ME.user_id)).toEqual([]);
  });

  it('a GENUINE auth rejection on boot still clears the queue (answers never outlive a real session end)', async () => {
    enqueueCheckIn(ME.user_id, QUEUED);
    // The server actively refuses this refresh token (revoked/expired) — a real
    // session end, unlike the offline case above.
    sessionStorage.setItem(REFRESH_TOKEN_KEY, 'revoked-refresh-token');

    renderApp('/', { authenticated: false });

    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(listQueuedCheckIns(ME.user_id)).toEqual([]);
    expect(sessionStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
  });

  it('signing in purges OTHER accounts’ queued offline check-ins left on this browser', async () => {
    const FOREIGN_OWNER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    enqueueCheckIn(FOREIGN_OWNER, QUEUED);
    const user = userEvent.setup();
    renderApp('/login', { authenticated: false });
    await user.type(screen.getByLabelText('Email'), TEST_EMAIL);
    await user.type(screen.getByLabelText('Password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Improving')).toBeInTheDocument();
    // The confirmed profile (ME) is not FOREIGN_OWNER — the foreign PHI is gone.
    expect(listQueuedCheckIns(FOREIGN_OWNER)).toEqual([]);
  });

  it('signs out from the avatar button', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByText('Improving');
    await user.click(screen.getByRole('button', { name: /Sign out/ }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    });
    expect(sessionStorage.getItem('neuropathy.refresh_token')).toBeNull();
  });
});
