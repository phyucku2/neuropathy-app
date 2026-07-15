/**
 * ErrorBoundary (ADR-0032): the boundary that catches a REJECTED lazy-chunk import so a
 * post-deploy stale-chunk 404 (or a flaky network) does not white-screen the app.
 *
 * These tests exercise the boundary logic two ways:
 *  1. a child that throws synchronously — the direct render-error path, and
 *  2. a `React.lazy` component whose dynamic import REJECTS — the real failure mode, which
 *     Suspense surfaces as a thrown rejection the boundary must catch (Suspense handles
 *     PENDING, not REJECTED). A real broken chunk cannot be served in the jsdom or the
 *     Playwright harness (the E2E mock always serves a valid bundle), so this rejecting-lazy
 *     unit test is the only place the lazy-rejection → fallback path is provable.
 *
 * React logs a caught render error to `console.error` itself (its own dev logging, not our
 * code — our `componentDidCatch` deliberately stays silent per eslint no-console / CLAUDE.md
 * §5); that noise is expected and does not fail the run.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Suspense, lazy } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

function Boom(): never {
  throw new Error('boom with a secret token that must never reach the fallback');
}

describe('ErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders its children unchanged when nothing throws', () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText('all good')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the calm, branded, non-technical fallback when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent(
      'Something went wrong loading the app. Please reload to continue.',
    );
    // NON-technical: the error message / stack must never leak to the user.
    expect(screen.queryByText(/secret token/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Error:/)).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Something went wrong' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('reloads the page when the reload button is clicked (recovers the stale-chunk case)', async () => {
    const user = userEvent.setup();
    // window.location.reload is non-configurable in jsdom, so swap the whole location object
    // for one whose reload is a spy, then restore it after asserting.
    const original = window.location;
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...original, reload },
    });

    try {
      render(
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>,
      );

      await user.click(screen.getByRole('button', { name: 'Reload' }));
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: original });
    }
  });

  it('catches a REJECTED lazy import surfaced through Suspense (the real post-deploy failure mode)', async () => {
    // A React.lazy whose dynamic import rejects mimics a hashed chunk that 404s after a
    // redeploy. Suspense renders the fallback while pending, then re-throws the rejection —
    // which only the boundary above it can catch.
    const BrokenLazy = lazy(() => Promise.reject(new Error('chunk 404 after deploy')));

    render(
      <ErrorBoundary>
        <Suspense fallback={<p>loading…</p>}>
          <BrokenLazy />
        </Suspense>
      </ErrorBoundary>,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong loading the app. Please reload to continue.',
    );
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });
});
