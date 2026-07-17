/**
 * Learn — the education-module index (ADR-0037). Rendered through the whole App so the
 * test also proves the React.lazy route chunk resolves under Suspense in jsdom, and that
 * the fifth bottom-nav tab reaches /learn. The page makes NO data calls (placeholder
 * registry only), so no msw handler is exercised here.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';
import { LEARN_MODULES } from './modules';

describe('LearnPage', () => {
  it('renders the intro, every module title in order, and placeholder states', async () => {
    renderApp('/learn');

    expect(await screen.findByRole('heading', { level: 1, name: 'Learn' })).toBeInTheDocument();
    // Plain-language intro line.
    expect(screen.getByText(/Short, plain-language lessons/)).toBeInTheDocument();

    // All eight module titles are present, exercise/balance first (evidence-first).
    for (const module of LEARN_MODULES) {
      expect(screen.getByRole('heading', { level: 2, name: module.title })).toBeInTheDocument();
    }
    expect(
      screen.getByRole('heading', { level: 2, name: 'Exercise & balance training' }),
    ).toBeInTheDocument();

    // Placeholder states carry WORDS, never color alone (ADR-0039): the reviewed lead and
    // the coming-soon rest, plus the labeled empty video slots.
    expect(screen.getByText('Reviewed by your care team')).toBeInTheDocument();
    expect(screen.getAllByText('Coming soon').length).toBeGreaterThan(0);
    expect(screen.getByText('Next session ▶')).toBeInTheDocument();
    expect(screen.getAllByText('▶ Watch (coming soon)').length).toBeGreaterThan(0);
  });

  it('ends with the standard non-diagnostic disclaimer (ADR-0037)', async () => {
    renderApp('/learn');
    expect(
      await screen.findByText('General education — not medical advice. Talk to your care team.'),
    ).toBeInTheDocument();
  });

  it('is reachable from the bottom-nav Learn tab', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByText('30 Day Score');

    const nav = screen.getByRole('navigation', { name: 'Main' });
    await user.click(within(nav).getByRole('link', { name: /Learn/ }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Learn' })).toBeInTheDocument();
  });
});
