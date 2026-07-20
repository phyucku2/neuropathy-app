import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('EventsPage — between-visit notes & events', () => {
  it('always shows the persistent, non-dismissible emergency banner on the compose surface', async () => {
    renderApp('/events');
    const banner = await screen.findByRole('note', { name: 'Emergency information' });
    expect(banner).toHaveTextContent(/not monitored in real time/);
    expect(banner).toHaveTextContent(/call 911/);
    // Non-dismissible: there is no close/dismiss control on the banner.
    expect(banner.querySelector('button')).toBeNull();
  });

  it('lists recorded events newest-first with the note shown verbatim under an own-words label', async () => {
    renderApp('/events');
    // The note is the patient's own words, rendered verbatim (unique to the list, unlike the
    // "Fall" label which also appears as a select option).
    expect(
      await screen.findByText('Lost my balance stepping off the curb, no injury.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Feet feel colder in the mornings this week.')).toBeInTheDocument();
    expect(screen.getAllByText(/In your own words:/).length).toBeGreaterThan(0);
  });

  it('requires a non-empty note for a note-type event', async () => {
    const user = userEvent.setup();
    renderApp('/events');
    // Default type is a fall — Save is enabled with no note.
    const save = await screen.findByRole('button', { name: 'Save' });
    expect(save).toBeEnabled();
    // Switch to a plain note — now a note is required.
    await user.selectOptions(screen.getByLabelText('What happened?'), 'note');
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText('Note (in your own words)'), 'Numbness worse today');
    expect(save).toBeEnabled();
  });

  it('records an event and confirms it was saved', async () => {
    let captured: { type: string; note: string | null; client_entry_id: string } | null = null;
    server.use(
      http.post('/events', async ({ request }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json(
          {
            event_id: 'e-new',
            type: 'fall',
            effective_at: '2026-07-10T00:00:00Z',
            note: 'Slipped on the stairs',
            reviewed: false,
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp('/events');
    await user.type(await screen.findByLabelText(/Note \(optional/), 'Slipped on the stairs');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Saved to your between-visit list.')).toBeInTheDocument();
    expect((captured as unknown as { type: string }).type).toBe('fall');
    expect((captured as unknown as { note: string }).note).toBe('Slipped on the stairs');
  });

  it('shows the capability-off copy when the source is turned off (409)', async () => {
    server.use(
      http.get('/events', () =>
        HttpResponse.json({ detail: 'Notes & events is turned off' }, { status: 409 }),
      ),
    );
    renderApp('/events');
    expect(
      await screen.findByRole('heading', { name: 'Notes & events is turned off' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /turn it back on in Sources/ })).toHaveAttribute(
      'href',
      '/settings',
    );
    // The emergency banner still shows even when capture is off.
    expect(screen.getByRole('note', { name: 'Emergency information' })).toBeInTheDocument();
  });
});
