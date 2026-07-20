import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { TRAJECTORY_IMPROVING, TRAJECTORY_INSUFFICIENT } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('HomePage', () => {
  it('renders the Neuropathy Status Index hero, signals, and gaps', async () => {
    renderApp('/');
    // The number-forward card: eyebrow, big score, direction word, delta.
    expect(await screen.findByText('30 Day Score')).toBeInTheDocument();
    // Personalized greeting uses the signed-in patient's first name (ME = 'Pat Example').
    expect(await screen.findByRole('heading', { name: 'Hi, Pat' })).toBeInTheDocument();
    const hero = screen.getByRole('region', { name: /Your 30 day score/ });
    // Card colour is driven by the composite's OWN delta (improving -> improving class).
    expect(hero).toHaveClass('traj', 'improving');
    expect(screen.getByText('74')).toBeInTheDocument();
    expect(screen.getByText('/100')).toBeInTheDocument();
    // Direction in WORDS + glyph (never colour alone, WCAG 1.4.1).
    expect(screen.getByText('improving')).toBeInTheDocument();
    expect(screen.getByText('+7 pts')).toBeInTheDocument();
    expect(screen.getByText(/vs 30 days ago/)).toBeInTheDocument();
    // Confidence chip + as_of date.
    expect(screen.getByText('Confidence: High')).toBeInTheDocument();
    expect(screen.getByText(/as of Jul 12/)).toBeInTheDocument();
    // The section's accessible name speaks score + direction + delta + as_of + Confidence.
    expect(hero).toHaveAccessibleName(
      'Your 30 day score: score 74 out of 100, improving, +7 points vs 30 days ago, as of Jul 12, confidence high',
    );

    // Signals: sourced chip + plain-language label + direction arrow.
    expect(screen.getByText('Balance score')).toBeInTheDocument();
    expect(screen.getByText('BioMech')).toBeInTheDocument();
    expect(screen.getByText('balance up 8 over 30 days')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'declining' })).toHaveTextContent('↓');
    // Lab signal label comes from the LOINC registry mirror, never the raw code.
    expect(screen.getByText('Long-term blood sugar')).toBeInTheDocument();
    // Symptom-domain signal (ADR-0034) surfaces its distinct plain-language label.
    expect(screen.getByText('nerve pain')).toBeInTheDocument();

    // Data gaps card.
    expect(screen.getByText('Data gaps')).toBeInTheDocument();
    expect(screen.getByText('No lab results in the last 90 days')).toBeInTheDocument();

    expect(screen.getByText(/Not medical advice/)).toBeInTheDocument();
    // A non-diagnostic note is co-located with the computed direction (ADR-0016/0041),
    // not only in the footer — assert it sits right after the hero region.
    const note = screen.getByRole('note');
    expect(note).toHaveTextContent(/not a diagnosis/i);
    expect(hero.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // With data, the primary CTAs show and the empty-state Get-started card does not.
    expect(screen.getByRole('link', { name: 'See your trends' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Get started' })).not.toBeInTheDocument();
  });

  it('renders the insufficient-data variant without a signals card', async () => {
    server.use(http.get('/trajectory', () => HttpResponse.json(TRAJECTORY_INSUFFICIENT)));
    renderApp('/');
    expect(await screen.findByText('Not enough data yet')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Your 30 day score/ })).toHaveClass(
      'insufficient_data',
    );
    expect(screen.queryByText("What's driving it")).not.toBeInTheDocument();
    expect(screen.getByText('No BioMech reports yet')).toBeInTheDocument();

    // Empty state fills the space with onboarding (Get-started card), not a blank screen.
    const getStarted = screen.getByRole('region', { name: 'Get started' });
    expect(getStarted).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Do today.s check-in/ })).toHaveAttribute(
      'href',
      '/check-in',
    );
    expect(screen.getByRole('link', { name: /Connect your health record/ })).toHaveAttribute(
      'href',
      '/settings',
    );
    expect(screen.getByRole('link', { name: /Add a lab or report/ })).toHaveAttribute(
      'href',
      '/add',
    );
    // The bottom "See your trends" CTA is hidden when there is no trend to see.
    expect(screen.queryByRole('link', { name: 'See your trends' })).not.toBeInTheDocument();
  });

  it('renders an unjudged signal as "not enough data", never as "stable"', async () => {
    server.use(
      http.get('/trajectory', () =>
        HttpResponse.json({
          ...TRAJECTORY_IMPROVING,
          signals: [
            {
              code: 'biomech_cadence',
              source: 'biomech',
              direction: 'insufficient_data',
              detail: 'only one cadence reading so far',
            },
          ],
        }),
      ),
    );
    renderApp('/');
    const badge = await screen.findByRole('img', { name: 'not enough data' });
    expect(badge).toHaveTextContent('·');
    expect(badge).toHaveClass('arrow', 'unjudged');
    // The backend refused to judge this signal — no fabricated stability claim.
    expect(screen.queryByRole('img', { name: 'stable' })).not.toBeInTheDocument();
    expect(screen.queryByText('stable')).not.toBeInTheDocument();
  });

  it('shows the error state when the trajectory read fails', async () => {
    server.use(
      http.get('/trajectory', () =>
        HttpResponse.json({ detail: 'Trajectory unavailable' }, { status: 503 }),
      ),
    );
    renderApp('/');
    expect(await screen.findByRole('alert')).toHaveTextContent('Trajectory unavailable');
  });
});
