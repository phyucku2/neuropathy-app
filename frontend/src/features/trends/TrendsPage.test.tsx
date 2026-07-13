import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { ObservationItem } from '../../api/types';
import { OBSERVATIONS } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';
import { ChartTooltip, timeTicks, trendAriaLabel } from './TrendChart';
import { groupByCode } from './TrendsPage';

function observationsPage(items: ObservationItem[], total = items.length) {
  return http.get('/observations', () =>
    HttpResponse.json({ items, total, limit: 100, offset: 0 }),
  );
}

describe('TrendsPage', () => {
  it('offers one metric chip per code present in the data, newest first', async () => {
    renderApp('/trends');
    const picker = await screen.findByRole('group', { name: 'Pick a measure' });
    expect(picker).toBeInTheDocument();
    const chips = screen.getAllByRole('button', { pressed: false }).map((b) => b.textContent);
    expect(screen.getByRole('button', { pressed: true })).toHaveTextContent('Balance score');
    expect(chips).toContain('Sway velocity');
    expect(chips).toContain('Hemoglobin A1c');
  });

  it('renders an accessible chart summarizing the selected trend', async () => {
    renderApp('/trends');
    const chart = await screen.findByRole('img', { name: /^Balance score:/ });
    expect(chart).toHaveAccessibleName(
      'Balance score: 3 readings from May 6, 2026 to Jul 2, 2026, rising from 57 to 65 score',
    );
    // Direction-of-better annotation from signal semantics.
    expect(screen.getByText('Higher is better for this measure.')).toBeInTheDocument();
    // Latest value with unit ("{score}" renders without UCUM braces).
    expect(screen.getByText('65')).toBeInTheDocument();
    expect(screen.getByText('3 data points')).toBeInTheDocument();
    expect(screen.getByText('from BioMech')).toBeInTheDocument();
  });

  it('switches metric on chip click and flips the direction-of-better note', async () => {
    const user = userEvent.setup();
    renderApp('/trends');
    await screen.findByRole('img', { name: /^Balance score:/ });
    await user.click(screen.getByRole('button', { name: 'Sway velocity' }));
    expect(await screen.findByRole('img', { name: /^Sway velocity:/ })).toHaveAccessibleName(
      /falling from 12.9 to 11.4 mm\/s/,
    );
    expect(screen.getByText('Lower is better for this measure.')).toBeInTheDocument();
  });

  it('shows a visible empty state for a code with fewer than 2 points', async () => {
    const user = userEvent.setup();
    renderApp('/trends');
    await screen.findByRole('img', { name: /^Balance score:/ });
    await user.click(screen.getByRole('button', { name: 'Hemoglobin A1c' }));
    expect(await screen.findByText(/Not enough readings to draw a trend yet/)).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /^Hemoglobin A1c:/ })).not.toBeInTheDocument();
    // Direction-of-better still stated (HbA1c: lower is better).
    expect(screen.getByText('Lower is better for this measure.')).toBeInTheDocument();
  });

  it('shows the no-data state when there are no readings at all', async () => {
    server.use(observationsPage([]));
    renderApp('/trends');
    expect(await screen.findByText('No readings yet.')).toBeInTheDocument();
    expect(screen.getByText(/Add a BioMech report/)).toBeInTheDocument();
  });

  it('notes truncation when more readings exist than one page', async () => {
    server.use(observationsPage(OBSERVATIONS, 250));
    renderApp('/trends');
    await screen.findByRole('img', { name: /^Balance score:/ });
    expect(screen.getByText(/Showing your most recent 100 readings/)).toBeInTheDocument();
  });

  it('shows the error state when the read fails', async () => {
    server.use(
      http.get('/observations', () =>
        HttpResponse.json({ detail: 'Storage unavailable' }, { status: 503 }),
      ),
    );
    renderApp('/trends');
    expect(await screen.findByRole('alert')).toHaveTextContent('Storage unavailable');
  });
});

describe('groupByCode', () => {
  it('excludes text-only results and sorts points ascending in time', () => {
    const items: ObservationItem[] = [
      ...OBSERVATIONS,
      {
        code: 'urine_culture',
        display: 'Urine culture',
        value: null,
        value_text: 'negative',
        unit: null,
        effective_at: '2026-07-01T00:00:00Z',
        source: 'lab',
        status: 'final',
      },
    ];
    const series = groupByCode(items);
    expect(series.map((entry) => entry.code)).not.toContain('urine_culture');
    const balance = series.find((entry) => entry.code === 'biomech_balance_score');
    expect(balance?.points.map((point) => point.value)).toEqual([57, 64, 65]);
  });
});

describe('TrendChart helpers', () => {
  const points = [
    { t: Date.UTC(2026, 3, 1), value: 57 },
    { t: Date.UTC(2026, 4, 1), value: 60 },
    { t: Date.UTC(2026, 5, 1), value: 62 },
    { t: Date.UTC(2026, 6, 1), value: 65 },
    { t: Date.UTC(2026, 6, 15), value: 64 },
  ];

  it('timeTicks spans the range with evenly spaced ticks', () => {
    const firstTick = Date.UTC(2026, 3, 1);
    const ticks = timeTicks(points);
    expect(ticks).toHaveLength(4);
    expect(ticks[0]).toBe(firstTick);
    expect(ticks[3]).toBe(Date.UTC(2026, 6, 15));
    expect(timeTicks(points.slice(0, 2))).toEqual([Date.UTC(2026, 3, 1), Date.UTC(2026, 4, 1)]);
    expect(timeTicks([])).toEqual([]);
    const sameInstant = [
      { t: firstTick, value: 57 },
      { t: firstTick, value: 1 },
    ];
    expect(timeTicks(sameInstant)).toEqual([firstTick]);
  });

  it('trendAriaLabel covers rising, falling, steady, and unitless series', () => {
    expect(trendAriaLabel('Balance score', 'score', points)).toMatch(/rising from 57 to 64 score/);
    const falling = [...points].map((p, i) => ({ ...p, value: 70 - i }));
    expect(trendAriaLabel('Sway velocity', 'mm/s', falling)).toMatch(/falling/);
    const steady = points.map((p) => ({ ...p, value: 5 }));
    expect(trendAriaLabel('Cadence', '', steady)).toMatch(/steady at 5$/);
    expect(trendAriaLabel('Anything', '', [])).toBe('Anything: no readings yet');
  });

  it('ChartTooltip renders value + unit + date and hides when inactive', () => {
    const point = { t: Date.UTC(2026, 6, 2), value: 11.4 };
    const { container, rerender } = render(
      <ChartTooltip active payload={[{ payload: point }]} unitText="mm/s" />,
    );
    expect(container).toHaveTextContent('11.4 mm/s');
    expect(container).toHaveTextContent('Jul 2, 2026');
    rerender(<ChartTooltip active={false} payload={[{ payload: point }]} unitText="mm/s" />);
    expect(container).toBeEmptyDOMElement();
  });
});
