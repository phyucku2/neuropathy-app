/**
 * About screen (ADR-0032): renders auth-less, carries the non-diagnostic
 * disclaimer, shows the build-time version, and cross-links to Privacy. Rendered
 * through the whole App so the test also proves the React.lazy route chunk
 * resolves under Suspense in jsdom (the lazy-route smoke).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';

describe('AboutPage', () => {
  it('renders auth-less with app identity, version, and the non-diagnostic disclaimer', async () => {
    renderApp('/about', { authenticated: false });

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Neuropathy' }),
    ).toBeInTheDocument();
    // Build-time version injected via Vite `define` from package.json.
    expect(screen.getByText(/Version \d+\.\d+\.\d+/)).toBeInTheDocument();
    // Non-diagnostic posture, mirroring ADR-0016 wording.
    expect(
      screen.getByText('Trends support clinical judgment; they are not a diagnosis.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/does not diagnose, treat, or prevent/)).toBeInTheDocument();
    // What the app does, in plain language.
    expect(screen.getByRole('heading', { name: 'What Neuropathy does' })).toBeInTheDocument();
    // IP / licensee line (ADR-0001).
    expect(screen.getByText(/BioMech Health is a licensee/)).toBeInTheDocument();
    // Support placeholder.
    expect(screen.getByText(/placeholder — set before store submission/)).toBeInTheDocument();
  });

  it('cross-links to the privacy summary', async () => {
    const user = userEvent.setup();
    renderApp('/about', { authenticated: false });

    await user.click(await screen.findByRole('link', { name: 'Read the privacy summary' }));
    expect(
      await screen.findByRole('heading', { name: 'Your privacy, in plain language' }),
    ).toBeInTheDocument();
  });
});
