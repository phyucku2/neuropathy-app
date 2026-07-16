/**
 * The Neuropathy Status Index hero card (ADR-0034) — number-forward, honest, and
 * incapable of contradicting itself. These lock the behaviors the ADR was written to
 * guarantee: colour + arrow + word all driven by the ONE composite delta, direction in
 * words (never colour alone, WCAG 1.4.1), an accessible name that speaks the whole
 * picture, and stale data that says it is stale rather than reading as fresh.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Trajectory } from '../api/types';
import { TrajectoryHero } from './TrajectoryView';

const BASE: Trajectory = {
  direction: 'improving',
  confidence: 0.8,
  summary: 'unused on the card',
  signals: [],
  data_gaps: [],
  narrative_source: 'deterministic',
  score: 74,
  score_delta_30d: 7,
  as_of: '2026-07-12',
  confidence_level: 'high',
  direction_word: 'improving',
  data_is_stale: false,
};

function hero(overrides: Partial<Trajectory>) {
  return render(
    <TrajectoryHero
      trajectory={{ ...BASE, ...overrides }}
      eyebrow="30 Day Score"
      ariaLabel="Your 30 day score"
    />,
  );
}

describe('TrajectoryHero — Neuropathy Status Index card', () => {
  it('drives colour, arrow, and word from a POSITIVE delta (improving)', () => {
    hero({});
    const region = screen.getByRole('region', { name: /Your 30 day score/ });
    expect(region).toHaveClass('traj', 'improving');
    expect(screen.getByText('74')).toBeInTheDocument();
    expect(screen.getByText('/100')).toBeInTheDocument();
    expect(screen.getByText('↑')).toBeInTheDocument();
    expect(screen.getByText('improving')).toBeInTheDocument();
    expect(screen.getByText('+7 pts')).toBeInTheDocument();
    expect(region).toHaveAccessibleName(
      'Your 30 day score: score 74 out of 100, improving, +7 points vs 30 days ago, as of Jul 12, confidence high',
    );
  });

  it('drives colour, arrow, and word from a NEGATIVE delta (declining)', () => {
    hero({
      score: 61,
      score_delta_30d: -6,
      direction_word: 'declining',
      confidence_level: 'medium',
    });
    const region = screen.getByRole('region', { name: /Your 30 day score/ });
    expect(region).toHaveClass('traj', 'declining');
    expect(screen.getByText('↓')).toBeInTheDocument();
    expect(screen.getByText('declining')).toBeInTheDocument();
    expect(screen.getByText('−6 pts')).toBeInTheDocument();
    expect(screen.getByText('Confidence: Medium')).toBeInTheDocument();
  });

  it('renders a ZERO delta as steady with the → glyph (never colour alone)', () => {
    hero({ score: 70, score_delta_30d: 0, direction_word: 'stable' });
    const region = screen.getByRole('region', { name: /Your 30 day score/ });
    expect(region).toHaveClass('traj', 'stable');
    expect(screen.getByText('→')).toBeInTheDocument();
    expect(screen.getByText('steady')).toBeInTheDocument();
    expect(screen.getByText('0 pts')).toBeInTheDocument();
  });

  it('says the data may be out of date when it is stale, and degrades confidence', () => {
    hero({ data_is_stale: true, confidence_level: 'low' });
    expect(screen.getByText('Confidence: Low')).toBeInTheDocument();
    expect(screen.getByText(/may be out of date/)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /data may be out of date/ })).toBeInTheDocument();
  });

  it('shows the honest "not enough data" card when there is no score', () => {
    hero({
      score: null,
      score_delta_30d: null,
      as_of: null,
      confidence_level: null,
      direction_word: null,
    });
    const region = screen.getByRole('region', { name: /Your 30 day score: not enough data yet/ });
    expect(region).toHaveClass('traj', 'insufficient_data');
    expect(screen.getByText('Not enough data yet')).toBeInTheDocument();
  });
});
