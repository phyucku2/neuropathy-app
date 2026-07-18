import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { ME } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { ONBOARDING_COMPLETE_KEY, isOnboardingComplete } from './onboardingState';

describe('First-run onboarding wizard (ADR-0044)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('shows the welcome wizard to a not-yet-onboarded patient (before the app)', async () => {
    renderApp('/', { onboarded: false });
    // The wizard renders...
    expect(
      await screen.findByRole('heading', { name: 'A clearer picture, over time' }),
    ).toBeVisible();
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
    // ...instead of the home page.
    expect(screen.queryByRole('heading', { name: /Neuropathy status/i })).not.toBeInTheDocument();
  });

  it('walks the steps and finishing persists the flag and enters the app', async () => {
    const user = userEvent.setup();
    renderApp('/', { onboarded: false });
    await screen.findByRole('heading', { name: 'A clearer picture, over time' });

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByRole('heading', { name: 'Three easy ways' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByRole('heading', { name: 'Easy to use, and yours' })).toBeVisible();
    // The non-diagnostic note appears on the last step.
    expect(screen.getByRole('note')).toHaveTextContent(/does not diagnose/i);

    await user.click(screen.getByRole('button', { name: 'Get started' }));

    // The flag is persisted for this user...
    await waitFor(() => {
      expect(isOnboardingComplete(ME.user_id)).toBe(true);
    });
    // ...and the app (not the wizard) now renders.
    await waitFor(() => {
      expect(
        screen.queryByRole('heading', { name: 'A clearer picture, over time' }),
      ).not.toBeInTheDocument();
    });
  });

  it('lets a patient skip, which also persists the flag', async () => {
    const user = userEvent.setup();
    renderApp('/', { onboarded: false });
    await screen.findByRole('heading', { name: 'A clearer picture, over time' });
    await user.click(screen.getByRole('button', { name: 'Skip for now' }));
    await waitFor(() => {
      expect(isOnboardingComplete(ME.user_id)).toBe(true);
    });
  });

  it('does NOT show the wizard to a returning (already-onboarded) patient', async () => {
    // The default onboarded=true path — the wizard must not appear.
    renderApp('/records');
    await screen.findByText(/./); // let the app render
    expect(
      screen.queryByRole('heading', { name: 'A clearer picture, over time' }),
    ).not.toBeInTheDocument();
    // The flag was seeded by the harness.
    expect(localStorage.getItem(ONBOARDING_COMPLETE_KEY)).toContain(ME.user_id);
  });
});
