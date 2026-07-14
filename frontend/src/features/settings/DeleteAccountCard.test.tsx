/**
 * Danger zone (ADR-0027): the delete-account flow — acknowledgment gating, the
 * two-tap confirm, pending-disable, the verbatim wrong-password alert, and the
 * happy path landing on the login screen with the transient deleted notice.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { getRefreshToken } from '../../auth/tokenStore';
import { DELETE_WRONG_PASSWORD_DETAIL, TEST_PASSWORD } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

async function openDangerZone() {
  const user = userEvent.setup();
  renderApp('/settings');
  await user.click(await screen.findByRole('button', { name: 'Delete my account' }));
  return user;
}

describe('SettingsPage — danger zone (delete account)', () => {
  it('keeps the confirm button disabled until BOTH the password and the acknowledgment are given', async () => {
    const user = await openDangerZone();
    const confirm = screen.getByRole('button', { name: 'Delete my account and data' });
    expect(confirm).toBeDisabled();

    // Password alone is not enough...
    await user.type(screen.getByLabelText('Confirm your password'), TEST_PASSWORD);
    expect(confirm).toBeDisabled();
    // ...the checkbox alone is not enough either.
    const acknowledge = screen.getByRole('checkbox');
    await user.click(acknowledge);
    expect(confirm).toBeEnabled();
    await user.clear(screen.getByLabelText('Confirm your password'));
    expect(confirm).toBeDisabled();
  });

  it('requires a second tap to confirm, then deletes and lands on login with the notice', async () => {
    const user = await openDangerZone();
    await user.type(screen.getByLabelText('Confirm your password'), TEST_PASSWORD);
    await user.click(screen.getByRole('checkbox'));

    // First tap arms the confirm — nothing is deleted yet.
    await user.click(screen.getByRole('button', { name: 'Delete my account and data' }));
    const armed = screen.getByRole('button', { name: 'Tap again to permanently delete' });
    expect(screen.getByRole('heading', { name: 'Your data sources' })).toBeInTheDocument();

    await user.click(armed);
    // The session is gone and the login screen shows the transient confirmation.
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Your account and data were deleted.');
    expect(getRefreshToken()).toBeNull();
  });

  it('shows the wrong-password detail verbatim in an alert and stays on settings', async () => {
    const user = await openDangerZone();
    await user.type(screen.getByLabelText('Confirm your password'), 'not-the-password');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'Delete my account and data' }));
    await user.click(screen.getByRole('button', { name: 'Tap again to permanently delete' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(DELETE_WRONG_PASSWORD_DETAIL); // verbatim
    // Still on settings, the session intact, the confirm disarmed back to step one.
    expect(screen.getByRole('heading', { name: 'Your data sources' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete my account and data' })).toBeInTheDocument();
    expect(getRefreshToken()).not.toBeNull();
  });

  it('disables every control while the request is pending', async () => {
    server.use(
      http.delete('/auth/me', async () => {
        await delay(150);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = await openDangerZone();
    const passwordInput = screen.getByLabelText('Confirm your password');
    await user.type(passwordInput, TEST_PASSWORD);
    const acknowledge = screen.getByRole('checkbox');
    await user.click(acknowledge);
    await user.click(screen.getByRole('button', { name: 'Delete my account and data' }));
    await user.click(screen.getByRole('button', { name: 'Tap again to permanently delete' }));

    // Pending: the button shows progress and EVERY control is disabled.
    const pendingButton = screen.getByRole('button', { name: 'Deleting…' });
    expect(pendingButton).toBeDisabled();
    expect(passwordInput).toBeDisabled();
    expect(acknowledge).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Keep my account' })).toBeDisabled();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    });
  });

  it('lets the user back out without deleting anything', async () => {
    const user = await openDangerZone();
    await user.type(screen.getByLabelText('Confirm your password'), TEST_PASSWORD);
    await user.click(screen.getByRole('button', { name: 'Keep my account' }));
    // Collapsed back to the entry point; the session is untouched.
    expect(screen.getByRole('button', { name: 'Delete my account' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Confirm your password')).not.toBeInTheDocument();
    expect(getRefreshToken()).not.toBeNull();
  });
});
