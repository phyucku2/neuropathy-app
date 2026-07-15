/**
 * The shared frame for the auth-less informational screens (About, Privacy).
 *
 * These pages are reachable WITHOUT signing in (a store reviewer and a logged-out
 * patient must reach them — ADR-0026/ADR-0032), so they render their OWN frame
 * rather than the signed-in AppShell. The frame reuses the established app-frame /
 * status-bar / app-body classes (ADR-0015) so it inherits the brand header, the
 * scrolling body, and the safe-area insets (ADR-0025) with no new CSS. Content is
 * static and PHI-free: no data calls happen here.
 */

import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function InfoLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="app-frame">
      <header className="status-bar">
        <span className="mark">◍ Neuropathy</span>
        <Link className="link" to="/login" style={{ color: 'var(--color-text-on-dark)' }}>
          Sign in
        </Link>
      </header>
      <main
        className="app-body"
        aria-label={title}
        style={{ paddingBottom: 'calc(var(--space-lg) + env(safe-area-inset-bottom, 0px))' }}
      >
        {children}
      </main>
    </div>
  );
}
