/**
 * The signed-in frame from the mockup: gradient status bar with our own
 * wordmark (Poppins — never BioMech's logo, ADR-0002), scrolling body, and the
 * four-tab bottom bar (Home / Trends / Add / Sources).
 */

import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

function initials(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((part) => part.charAt(0).toUpperCase());
  return letters.join('') || '?';
}

const TABS = [
  { to: '/', icon: '◍', label: 'Home' },
  { to: '/trends', icon: '📈', label: 'Trends' },
  { to: '/add', icon: '＋', label: 'Add' },
  { to: '/settings', icon: '⚙', label: 'Sources' },
];

export function AppShell() {
  const { user, logout } = useAuth();

  return (
    <div className="app-frame">
      <header className="status-bar">
        <span className="mark">◍ Neuropathy</span>
        <button
          type="button"
          className="avatar"
          onClick={logout}
          title="Sign out"
          aria-label={`Sign out ${user?.display_name ?? ''}`.trim()}
        >
          {initials(user?.display_name ?? '')}
        </button>
      </header>
      <main className="app-body">
        <Outlet />
      </main>
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
    </div>
  );
}
