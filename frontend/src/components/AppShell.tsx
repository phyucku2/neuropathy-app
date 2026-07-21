/**
 * The signed-in frame, in three variants:
 * - patient (mockup patient-app.html): gradient status bar with our own
 *   wordmark (Poppins — never BioMech's logo, ADR-0002), scrolling body, and
 *   the four-tab bottom bar (Home / Trends / Add / Sources).
 * - clinician (mockup clinician-app.html): the same bar marked "· Clinician"
 *   with the signed-in clinician's name, a wider working area, and no patient
 *   tab bar — the panel is the clinician's home and detail screens link back.
 * - caregiver (ADR-0047): the patient-width frame marked "· Caregiver", no tab
 *   bar, and the PERSISTENT non-urgent/911 banner rendered by the shell itself
 *   so every caregiver screen structurally carries it (never per-page opt-in).
 */

import { Link, NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { EmergencyBanner } from './EmergencyBanner';
import { initials } from '../lib/format';

// Entry point for the Learn surface (ADR-0037): a fifth bottom-nav tab, chosen over a
// Home-screen card. Five tabs stay legible and comfortably tappable in the 430px frame
// (~86px each, well above the 44px floor; the tab keeps its 48px min-height, ADR-0039),
// and a persistent tab is reachable in one tap from ANY screen — better for 60+ users
// than a card only present on Home. Learn sits center (position 3 of 5), which also gives
// the evidence-first education surface visual prominence.
const TABS = [
  { to: '/', icon: '◍', label: 'Home' },
  { to: '/trends', icon: '📈', label: 'Trends' },
  { to: '/learn', icon: '📖', label: 'Learn' },
  { to: '/add', icon: '＋', label: 'Add' },
  { to: '/settings', icon: '⚙', label: 'Sources' },
];

export function AppShell({
  variant = 'patient',
}: {
  variant?: 'patient' | 'clinician' | 'caregiver';
}) {
  const { user, logout } = useAuth();
  const clinician = variant === 'clinician';
  const caregiver = variant === 'caregiver';

  return (
    <div className={clinician ? 'app-frame clinician' : 'app-frame'}>
      <header className="status-bar">
        <span className="mark">
          ◍ Neuropathy{clinician ? ' · Clinician' : caregiver ? ' · Caregiver' : ''}
        </span>
        <span className="status-right">
          {(clinician || caregiver) && <span className="who">{user?.display_name}</span>}
          {/* Clinician account settings (§1B C6): the clinician frame has no tab bar, so
              the settings surface hangs off the header instead. Patient shell unchanged. */}
          {clinician && (
            <Link className="link" to="/clinic/settings">
              Settings
            </Link>
          )}
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
        {/* Non-urgent framing is non-negotiable (ADR-0047): the shell renders the 911
            banner for the caregiver area, so EVERY caregiver screen carries it. */}
        {caregiver && <EmergencyBanner />}
        <Outlet />
      </main>
      {variant === 'patient' && (
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
