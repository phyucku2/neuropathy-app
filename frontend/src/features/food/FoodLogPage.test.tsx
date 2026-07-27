import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

/** A GET /food handler returning the given items (the page loads the list on mount). */
function foodList(items: unknown[] = []) {
  return http.get('/food', () => HttpResponse.json({ items }));
}

describe('FoodLogPage — ranged food log', () => {
  it('renders the heading, the non-dosing note, and the empty state', async () => {
    server.use(foodList([]));
    renderApp('/food');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Food & nutrition log' }),
    ).toBeInTheDocument();
    // The co-located non-diagnostic / non-dosing guardrail.
    expect(screen.getByRole('note')).toHaveTextContent(/never a basis for insulin or medication/i);
    expect(await screen.findByText(/Nothing logged yet/)).toBeInTheDocument();
  });

  it('renders a logged item as a range', async () => {
    server.use(
      foodList([
        {
          food_id: 'food-1',
          description: 'Oatmeal with banana',
          portion: '1 cup',
          carbs_g: { low: 30, high: 45 },
          energy_kcal: { low: 150, high: 250 },
          effective_at: '2026-07-10T00:00:00Z',
          skipped: false,
        },
      ]),
    );
    renderApp('/food');
    expect(await screen.findByText('Oatmeal with banana')).toBeInTheDocument();
    expect(screen.getByText(/Carbs ~30–45 g/)).toBeInTheDocument();
    expect(screen.getByText(/~150–250 kcal/)).toBeInTheDocument();
  });

  it('saves a confirmed, ranged food log', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      foodList([]),
      http.post('/food', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            food_id: 'food-new',
            description: 'Apple',
            portion: '1 medium',
            carbs_g: { low: 20, high: 30 },
            energy_kcal: null,
            effective_at: '2026-07-10T00:00:00Z',
            skipped: false,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp('/food');
    await user.type(await screen.findByLabelText('What did you eat?'), 'Apple');
    await user.type(screen.getByLabelText('Portion'), '1 medium');
    await user.type(screen.getByLabelText('Low (g)'), '20');
    await user.type(screen.getByLabelText('High (g)'), '30');
    await user.click(screen.getByRole('button', { name: 'Save this estimate' }));

    expect(await screen.findByText('Logged Apple.')).toBeInTheDocument();
    expect(captured).not.toBeNull();
    // The confirm-before-store guardrail is sent, and the nutrient is a range (no point value).
    expect((captured as unknown as { confirmed: boolean }).confirmed).toBe(true);
    expect((captured as unknown as { carbs_g: unknown }).carbs_g).toEqual({ low: 20, high: 30 });
    expect((captured as unknown as { energy_kcal: unknown }).energy_kcal).toBeNull();
  });

  it('shows the manual-entry fallback when the estimate seam returns none (Phase 1)', async () => {
    server.use(
      foodList([]),
      http.post('/food/estimate', () =>
        HttpResponse.json({ estimate: null, note: 'Enter your best guess as a range below.' }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/food');
    await user.type(await screen.findByLabelText('What did you eat?'), 'Pasta');
    await user.type(screen.getByLabelText('Portion'), '1 cup');
    await user.click(screen.getByRole('button', { name: 'Get a starting estimate' }));
    expect(await screen.findByText(/Enter your best guess as a range below/)).toBeInTheDocument();
  });

  it('shows the capability-off copy when the source is turned off (409)', async () => {
    server.use(
      http.get('/food', () =>
        HttpResponse.json({ detail: 'Food log is turned off' }, { status: 409 }),
      ),
    );
    renderApp('/food');
    expect(
      await screen.findByRole('heading', { name: 'Food log is turned off' }),
    ).toBeInTheDocument();
    const card = screen.getByRole('heading', { name: 'Food log is turned off' }).closest('.card');
    expect(
      within(card as HTMLElement).getByRole('link', { name: /turn it back on in Sources/ }),
    ).toHaveAttribute('href', '/settings');
    // The add form is hidden when the source is off.
    expect(screen.queryByRole('button', { name: 'Save this estimate' })).not.toBeInTheDocument();
  });
});
