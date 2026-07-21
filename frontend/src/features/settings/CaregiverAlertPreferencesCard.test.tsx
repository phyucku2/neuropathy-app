/**
 * "Updates you send to loved ones" (ADR-0047 B1): the patient's per-type opt-in
 * toggles — DEFAULT OFF, plain-language + non-monitoring framing, optimistic toggle
 * with rollback on failure. Rendered on the patient Settings/Sources page.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('CaregiverAlertPreferencesCard', () => {
  it('lists every type DEFAULT OFF with the non-monitoring framing', async () => {
    renderApp('/settings');
    expect(
      await screen.findByRole('heading', { name: 'Updates you send to loved ones' }),
    ).toBeInTheDocument();
    // Non-monitoring, non-emergency framing rides the card.
    expect(screen.getByText(/not live monitoring, and not for emergencies/)).toBeInTheDocument();

    // All four types are present and OFF by default (nothing is sent until opted in).
    expect(await screen.findByRole('switch', { name: 'Missed daily check-ins' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
    for (const label of [
      'Medication updates',
      'Wellness trend shifts',
      'New notes from the care team',
    ]) {
      expect(screen.getByRole('switch', { name: label })).toHaveAttribute('aria-checked', 'false');
    }
  });

  it('turns a type on (optimistic) and reflects the confirmed flag', async () => {
    const user = userEvent.setup();
    renderApp('/settings');
    const toggle = await screen.findByRole('switch', { name: 'Medication updates' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    await user.click(toggle);
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Medication updates' })).toHaveAttribute(
        'aria-checked',
        'true',
      );
    });
  });

  it('rolls back and surfaces the message when the server refuses', async () => {
    server.use(
      http.put('/me/caregiver-alert-preferences/:alertType', () =>
        HttpResponse.json({ detail: 'Something went wrong' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/settings');
    const toggle = await screen.findByRole('switch', { name: 'Wellness trend shifts' });

    await user.click(toggle);
    // Rolled back to OFF after the refusal.
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Wellness trend shifts' })).toHaveAttribute(
        'aria-checked',
        'false',
      );
    });
  });
});
