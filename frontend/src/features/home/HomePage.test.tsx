import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { TRAJECTORY_AI, TRAJECTORY_INSUFFICIENT } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

describe('HomePage', () => {
  it('renders the improving hero with summary, confidence, signals, and gaps', async () => {
    renderApp('/');
    expect(await screen.findByText('Improving')).toBeInTheDocument();
    const hero = screen.getByRole('region', { name: 'Your 30-day trend' });
    expect(hero).toHaveClass('traj', 'improving');
    expect(screen.getByText(/Balance and daily function are up/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Confidence 72 percent' })).toBeInTheDocument();
    expect(screen.getByText('Good')).toBeInTheDocument();

    // Signals: sourced chip + plain-language label + direction arrow.
    expect(screen.getByText('Balance score')).toBeInTheDocument();
    expect(screen.getByText('BioMech')).toBeInTheDocument();
    expect(screen.getByText('balance up 8 over 30 days')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'improving' })).toHaveTextContent('↑');
    expect(screen.getByRole('img', { name: 'declining' })).toHaveTextContent('↓');
    expect(screen.getByRole('img', { name: 'stable' })).toHaveTextContent('→');
    // Lab signal label comes from the LOINC registry mirror, never the raw code.
    expect(screen.getByText('Long-term blood sugar')).toBeInTheDocument();

    // Data gaps card.
    expect(screen.getByText('Data gaps')).toBeInTheDocument();
    expect(screen.getByText('No lab results in the last 90 days')).toBeInTheDocument();

    // No AI badge for a deterministic narrative.
    expect(screen.queryByText(/AI-written summary/)).not.toBeInTheDocument();
    expect(screen.getByText(/Not medical advice/)).toBeInTheDocument();
  });

  it('shows the narrative-source badge when the summary is AI-written', async () => {
    server.use(http.get('/trajectory', () => HttpResponse.json(TRAJECTORY_AI)));
    renderApp('/');
    expect(await screen.findByText(/AI-written summary/)).toBeInTheDocument();
  });

  it('renders the insufficient-data variant without a signals card', async () => {
    server.use(http.get('/trajectory', () => HttpResponse.json(TRAJECTORY_INSUFFICIENT)));
    renderApp('/');
    expect(await screen.findByText('Not enough data yet')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Your 30-day trend' })).toHaveClass(
      'insufficient_data',
    );
    expect(screen.queryByText("What's driving it")).not.toBeInTheDocument();
    expect(screen.getByText('No BioMech reports yet')).toBeInTheDocument();
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
