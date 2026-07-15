/**
 * Privacy summary screen (ADR-0026/ADR-0032): renders auth-less as an in-app
 * summary of docs/legal/privacy-policy-draft.md, is explicit that it points to the
 * full counsel-reviewed policy, and cross-links back to About. Rendered through the
 * whole App so it also proves the React.lazy route chunk resolves under Suspense.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../../test/renderApp';

describe('PrivacyPage', () => {
  it('renders auth-less as an honest summary that points to the full policy', async () => {
    renderApp('/privacy', { authenticated: false });

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Your privacy, in plain language' }),
    ).toBeInTheDocument();
    // Honest framing: a summary, not the complete counsel-reviewed policy.
    expect(screen.getByText(/It is not the complete policy/)).toBeInTheDocument();
    expect(
      screen.getByText(/full privacy policy URL — set before store submission/),
    ).toBeInTheDocument();
    // Key adapted sections.
    expect(screen.getByRole('heading', { name: 'What we collect' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Your controls' })).toBeInTheDocument();
    expect(screen.getByText(/You hold the sharing switch\./)).toBeInTheDocument();
    // Non-diagnostic posture restated.
    expect(
      screen.getByText(/does not diagnose, treat, or prevent any disease/),
    ).toBeInTheDocument();
  });

  it('cross-links back to About', async () => {
    const user = userEvent.setup();
    renderApp('/privacy', { authenticated: false });

    await user.click(await screen.findByRole('link', { name: 'Back to About' }));
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Neuropathy' }),
    ).toBeInTheDocument();
  });
});
