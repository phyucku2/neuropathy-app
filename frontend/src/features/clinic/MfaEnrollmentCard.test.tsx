import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { MFA_ENROLL, TEST_MFA_CODE } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { actAsClinician, server } from '../../test/server';

const SETTINGS_PATH = '/clinic/settings';

describe('Clinician settings — two-step verification enrollment (§1B C6)', () => {
  it('is reachable from the clinician header and shows the setup card', async () => {
    actAsClinician();
    const user = userEvent.setup();
    renderApp('/clinic');
    await screen.findByRole('heading', { name: 'Your panel' });
    await user.click(screen.getByRole('link', { name: 'Settings' }));
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Two-step verification' })).toBeVisible();
    expect(
      await screen.findByRole('button', { name: 'Set up two-step verification' }),
    ).toBeEnabled();
  });

  it('enrolls: the otpauth URI + secret show ONCE, then a code turns the factor on', async () => {
    actAsClinician();
    const user = userEvent.setup();
    renderApp(SETTINGS_PATH);
    await user.click(await screen.findByRole('button', { name: 'Set up two-step verification' }));

    // The one-time showing: URI + secret, with the shown-once warning.
    expect(await screen.findByLabelText('Authenticator link (otpauth URI)')).toHaveValue(
      MFA_ENROLL.otpauth_uri,
    );
    expect(screen.getByLabelText('Secret key (manual entry)')).toHaveValue(MFA_ENROLL.secret);
    expect(screen.getByText(/shown only once/)).toBeInTheDocument();

    await user.type(screen.getByLabelText('6-digit code from your app'), TEST_MFA_CODE);
    await user.click(screen.getByRole('button', { name: 'Turn on two-step verification' }));

    // The on-state replaces the setup flow…
    expect(await screen.findByText('On')).toBeInTheDocument();
    expect(
      screen.getByText('Signing in requires a code from your authenticator app.'),
    ).toBeInTheDocument();
    // …and the secret is GONE the moment the factor is live (shown once, never again).
    expect(screen.queryByLabelText('Secret key (manual entry)')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue(MFA_ENROLL.secret)).not.toBeInTheDocument();
  });

  it('keeps the secret on screen after a wrong confirmation code so the user can retry', async () => {
    actAsClinician();
    const user = userEvent.setup();
    renderApp(SETTINGS_PATH);
    await user.click(await screen.findByRole('button', { name: 'Set up two-step verification' }));
    await user.type(await screen.findByLabelText('6-digit code from your app'), '000000');
    await user.click(screen.getByRole('button', { name: 'Turn on two-step verification' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("That code didn't match");
    // Retry is possible: the factor is NOT on, and the secret is still visible.
    expect(screen.getByLabelText('Secret key (manual entry)')).toHaveValue(MFA_ENROLL.secret);
    expect(screen.queryByText('On')).not.toBeInTheDocument();
  });

  it('shows the on-state (and no setup button) for an already-enrolled account', async () => {
    actAsClinician();
    server.use(http.get('/auth/mfa', () => HttpResponse.json({ enrolled: true })));
    renderApp(SETTINGS_PATH);
    expect(await screen.findByText('On')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Set up two-step verification' }),
    ).not.toBeInTheDocument();
  });

  it('shows the error state when the status read fails', async () => {
    actAsClinician();
    server.use(
      http.get('/auth/mfa', () =>
        HttpResponse.json({ detail: 'Status unavailable' }, { status: 503 }),
      ),
    );
    renderApp(SETTINGS_PATH);
    expect(await screen.findByRole('alert')).toHaveTextContent('Status unavailable');
  });

  it('surfaces an enrollment-start failure and keeps the setup button', async () => {
    actAsClinician();
    server.use(
      http.post('/auth/mfa/enroll', () =>
        HttpResponse.json({ detail: 'Enrollment unavailable' }, { status: 503 }),
      ),
    );
    const user = userEvent.setup();
    renderApp(SETTINGS_PATH);
    await user.click(await screen.findByRole('button', { name: 'Set up two-step verification' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Enrollment unavailable');
    expect(screen.getByRole('button', { name: 'Set up two-step verification' })).toBeEnabled();
  });

  it('never renders for a patient — the clinician route guard redirects home', async () => {
    // Default ME is the patient account: /clinic/* bounces to the patient home.
    renderApp(SETTINGS_PATH);
    expect(await screen.findByText('30 Day Score')).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Two-step verification' }),
    ).not.toBeInTheDocument();
  });

  it('adds nothing to the patient settings surface (patients are not asked to enroll)', async () => {
    renderApp('/settings');
    await screen.findByRole('heading', { name: 'Your data sources' });
    expect(screen.queryByText('Two-step verification')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Settings' })).not.toBeInTheDocument();
  });
});
