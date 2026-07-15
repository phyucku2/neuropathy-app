/**
 * Top-level error boundary (ADR-0032).
 *
 * The app code-splits every route with `React.lazy` behind a `<Suspense>` (App.tsx).
 * Suspense only handles the PENDING state of a dynamic `import()`; it does NOT catch a
 * REJECTED one. A rejected chunk import — a flaky network, or the important case, a
 * redeploy that changes the hashed chunk filenames while a client still holds the old
 * `index.html` so the next navigation 404s a chunk — throws PAST Suspense and, with no
 * boundary, white-screens the whole app with an uncaught error. This boundary sits ABOVE
 * the Suspense so that rejection is caught and the user sees a calm, recoverable screen.
 *
 * Recovery is a full reload: fetching a fresh `index.html` picks up the CURRENT hashed
 * chunk names, which is exactly what recovers the post-deploy stale-chunk case.
 */

import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    // Do not stash the error object on state: it can carry PHI (CLAUDE.md §5) and would
    // then be one careless render away from the UI. We only need the boolean to switch
    // to the fallback.
    return { hasError: true };
  }

  override componentDidCatch(): void {
    // Intentionally NO console here (and the error/errorInfo args are deliberately not
    // captured): eslint `no-console` is an error in this repo, and a caught render error can
    // carry PHI or a token in its message/stack (CLAUDE.md §5), so it must never reach the
    // console or any un-scrubbed sink.
    // TODO(ADR-0021 error seam): when the frontend gains the outbound error seam, forward a
    // SCRUBBED, PHI-free signal here (fixed vocabulary / error name only, never
    // `error.message`, stack, or `componentStack`), mirroring the backend error-event
    // whitelist. Leave it unwired until that seam lands — do not add ad-hoc telemetry.
  }

  private handleReload = (): void => {
    // A full navigation re-fetches index.html and therefore the CURRENT hashed chunk
    // names, recovering the post-deploy stale-chunk 404 case (see the file header).
    window.location.reload();
  };

  override render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }
    // Branded, PHI-free fallback reusing the established frame + tokens (ADR-0015), so it
    // inherits the brand header, scrolling body, safe-area insets, and AA contrast with no
    // new CSS. Non-technical copy only — no stack trace, no error.message.
    return (
      <div className="app-frame">
        <header className="status-bar">
          <span className="mark">◍ Neuropathy</span>
        </header>
        <main className="app-body" aria-label="Something went wrong">
          <div className="card">
            <h1>Something went wrong</h1>
            <div className="form-error" role="alert">
              Something went wrong loading the app. Please reload to continue.
            </div>
            <p className="muted">
              This can happen right after an update. Reloading loads the latest version.
            </p>
            <button type="button" className="btn" onClick={this.handleReload}>
              Reload
            </button>
          </div>
        </main>
      </div>
    );
  }
}
