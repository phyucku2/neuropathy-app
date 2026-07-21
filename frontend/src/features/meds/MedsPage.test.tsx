import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('MedsPage — medication change log', () => {
  it('renders the folded list, per-med change log, and the non-diagnostic note', async () => {
    renderApp('/meds');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Medications & supplements' }),
    ).toBeInTheDocument();
    // Co-located non-diagnostic disclaimer.
    expect(screen.getByRole('note')).toHaveTextContent(/never adjusts, checks, or recommends/);

    // Folded current state: an active supplement and a stopped prescription.
    expect(await screen.findByText('Alpha-lipoic acid')).toBeInTheDocument();
    expect(screen.getByText('Gabapentin')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    // "Stopped" appears both as the Gabapentin status pill and as its change-log entry.
    expect(screen.getAllByText('Stopped').length).toBeGreaterThan(0);

    // The change log is present (a dose_changed entry on the supplement).
    expect(screen.getByText(/Dose changed/)).toBeInTheDocument();
  });

  it('adds a medication and shows the saved confirmation', async () => {
    let captured: { name: string; kind: string; client_entry_id: string } | null = null;
    server.use(
      http.post('/medications', async ({ request }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json(
          {
            medication_id: 'med:new',
            change_type: 'added',
            effective_at: '2026-07-10T00:00:00Z',
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp('/meds');
    await user.type(await screen.findByLabelText('Name'), 'Vitamin D');
    await user.selectOptions(screen.getByLabelText('Kind'), 'supplement');
    await user.click(screen.getByRole('button', { name: 'Add to my list' }));

    expect(await screen.findByText('Added Vitamin D to your list.')).toBeInTheDocument();
    expect(captured).not.toBeNull();
    expect((captured as unknown as { name: string }).name).toBe('Vitamin D');
    expect((captured as unknown as { kind: string }).kind).toBe('supplement');
  });

  it('appends a dose change to an existing medication', async () => {
    let changePath: string | null = null;
    server.use(
      http.post('/medications/:id/changes', async ({ params }) => {
        changePath = String(params['id']);
        return HttpResponse.json(
          {
            medication_id: String(params['id']),
            change_type: 'dose_changed',
            effective_at: '2026-07-10T00:00:00Z',
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp('/meds');
    await user.click(
      await screen.findByRole('button', { name: 'Record a change for Alpha-lipoic acid' }),
    );
    // Dose-change is the default; save is disabled until a dose field is present.
    const save = screen.getByRole('button', { name: 'Save this change' });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText('New dose amount'), '900');
    expect(save).toBeEnabled();
    await user.click(save);

    // The form closes on success (the change field is gone) and the change reached the API.
    expect(
      await screen.findByRole('button', { name: 'Record a change for Alpha-lipoic acid' }),
    ).toBeInTheDocument();
    expect(changePath).toBe('med:11111111-1111-4111-8111-aaaaaaaaaaaa');
  });

  it('marks a medication stopped without requiring a dose', async () => {
    let stoppedType: string | null = null;
    server.use(
      http.post('/medications/:id/changes', async ({ request, params }) => {
        const body = (await request.json()) as { change_type: string };
        stoppedType = body.change_type;
        return HttpResponse.json(
          {
            medication_id: String(params['id']),
            change_type: body.change_type,
            effective_at: '2026-07-10T00:00:00Z',
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp('/meds');
    await user.click(
      await screen.findByRole('button', { name: 'Record a change for Alpha-lipoic acid' }),
    );
    await user.click(screen.getByRole('radio', { name: 'Mark stopped' }));
    // No dose fields for a stop; save is immediately enabled.
    const save = screen.getByRole('button', { name: 'Save this change' });
    expect(save).toBeEnabled();
    await user.click(save);
    expect(
      await screen.findByRole('button', { name: 'Record a change for Alpha-lipoic acid' }),
    ).toBeInTheDocument();
    expect(stoppedType).toBe('stopped');
  });

  it('drives the change-type radiogroup with the roving-tabindex arrow-key pattern', async () => {
    const user = userEvent.setup();
    renderApp('/meds');
    await user.click(
      await screen.findByRole('button', { name: 'Record a change for Alpha-lipoic acid' }),
    );
    const group = screen.getByRole('radiogroup', { name: 'Change type for Alpha-lipoic acid' });
    const doseChange = within(group).getByRole('radio', { name: 'Dose change' });
    const stopped = within(group).getByRole('radio', { name: 'Mark stopped' });

    // Roving tabindex: the selected option is the group's single tab stop.
    expect(doseChange).toHaveAttribute('aria-checked', 'true');
    expect(doseChange).toHaveAttribute('tabindex', '0');
    expect(stopped).toHaveAttribute('tabindex', '-1');

    // Arrow keys move focus AND select (WAI-ARIA radio-group pattern, as on the check-in).
    doseChange.focus();
    await user.keyboard('{ArrowRight}');
    expect(stopped).toHaveAttribute('aria-checked', 'true');
    expect(stopped).toHaveFocus();
    expect(stopped).toHaveAttribute('tabindex', '0');
    expect(doseChange).toHaveAttribute('tabindex', '-1');

    // Wraps at the ends, in both directions.
    await user.keyboard('{ArrowDown}');
    expect(doseChange).toHaveAttribute('aria-checked', 'true');
    expect(doseChange).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(stopped).toHaveAttribute('aria-checked', 'true');
    expect(stopped).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(doseChange).toHaveAttribute('aria-checked', 'true');
    expect(doseChange).toHaveFocus();
  });

  it('shows the capability-off copy when the source is turned off (409)', async () => {
    server.use(
      http.get('/medications', () =>
        HttpResponse.json({ detail: 'Medications is turned off' }, { status: 409 }),
      ),
    );
    renderApp('/meds');
    expect(
      await screen.findByRole('heading', { name: 'Medications is turned off' }),
    ).toBeInTheDocument();
    const card = screen
      .getByRole('heading', { name: 'Medications is turned off' })
      .closest('.card');
    expect(
      within(card as HTMLElement).getByRole('link', { name: /turn it back on in Sources/ }),
    ).toHaveAttribute('href', '/settings');
    // The add form is not shown when the source is off.
    expect(screen.queryByRole('button', { name: 'Add to my list' })).not.toBeInTheDocument();
  });
});
