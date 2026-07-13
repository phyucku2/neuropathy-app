/**
 * The signed-in frame, in two variants:
 * - patient (mockup patient-app.html): gradient status bar with our own
 *   wordmark (Poppins — never BioMech's logo, ADR-0002), scrolling body, and
 *   the four-tab bottom bar (Home / Trends / Add / Sources).
 * - clinician (mockup clinician-app.html): the same bar marked "· Clinician"
 *   with the signed-in clinician's name, a wider working area, and no patient
 *   tab bar — the panel is the clinician's home and detail screens link back.
 */

import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { initials } from '../lib/format';

const TABS = [
  { to: '/', icon: '◍', label: 'Home' },
  { to: '/trends', icon: '📈', label: 'Trends' },
  { to: '/add', icon: '＋', label: 'Add' },
  { to: '/settings', icon: '⚙', label: 'Sources' },
];

export function AppShell({ variant = 'patient' }: { variant?: 'patient' | 'clinician' }) {
  const { user, logout } = useAuth();
  const clinician = variant === 'clinician';

  return (
    <div className={clinician ? 'app-frame clinician' : 'app-frame'}>
      <header className="status-bar">
        <span className="mark">◍ Neuropathy{clinician ? ' · Clinician' : ''}</span>
        <span className="status-right">
          {clinician && <span className="who">{user?.display_name}</span>}
          <button
            type="button"
            className="avatar"
            onClick={logout}
            title="Sign out"
            aria-label={`Sign out ${user?.display_name ?? ''}`.trim()}
          >
            {initials(user?.display_name ?? '')}
          </button>
        </span>
      </header>
      <main className="app-body">
        <Outlet />
      </main>
      {!clinician && (
        <nav className="tabbar" aria-label="Main">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.to === '/'}
              className={({ isActive }) => (isActive ? 'tab active' : 'tab')}
            >
              <span className="ic" aria-hidden="true">
                {tab.icon}
              </span>
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}
