/**
 * Small, unobtrusive floating demo overlays — rendered with plain DOM into their OWN
 * nodes (outside the React #root) so they never touch the real app tree, and only in
 * the demo build (this module is imported solely by main-demo.tsx). Two pieces:
 *
 * - `mountDemoBanner()` — a top-left "sample data, not a real patient" pill, so anyone
 *   opening the shared demo link immediately understands what they're looking at.
 * - `mountDemoBar()` — a top-right role switcher (Patient / Clinician / Caregiver) that
 *   writes the role to localStorage and reloads; the fetch mock then returns the
 *   matching identity for GET /auth/me, so each area is reachable without a login step.
 */

import { currentRole, seedSession, setRole, type DemoRole } from './mock';

const STYLE = `
.demo-bar, .demo-banner {
  position: fixed; top: 10px; z-index: 2147483647;
  display: flex; align-items: center; gap: 6px;
  border-radius: 999px;
  background: rgba(17, 35, 46, 0.92); color: #eef4f5;
  font: 600 12px/1 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  box-shadow: 0 6px 20px rgba(10, 40, 50, 0.35); backdrop-filter: blur(6px);
  user-select: none;
}
.demo-bar { right: 10px; padding: 5px 6px 5px 10px; }
.demo-banner { left: 10px; padding: 7px 13px; max-width: min(60vw, 340px); }
.demo-banner .demo-warn-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #d9a441; flex: 0 0 auto;
  box-shadow: 0 0 0 3px rgba(217, 164, 65, 0.22);
}
.demo-banner .demo-warn-text { color: #eef4f5; }
.demo-banner .demo-warn-text b { color: #f4d68a; font-weight: 700; }
.demo-bar .demo-tag {
  text-transform: uppercase; letter-spacing: 0.12em; font-size: 10px;
  color: #8fb9bf; margin-right: 2px;
}
.demo-bar button {
  appearance: none; border: 0; cursor: pointer; border-radius: 999px;
  padding: 6px 12px; font: inherit; color: #cde0e3; background: transparent;
  transition: background 0.15s, color 0.15s;
}
.demo-bar button:hover { color: #fff; }
.demo-bar button.on { background: #0e7c86; color: #fff; }
@media (max-width: 560px) {
  .demo-banner { font-size: 10.5px; padding: 6px 10px; max-width: 52vw; }
}
`;

/** Inject the shared overlay stylesheet once, whichever mount runs first. */
function ensureStyle(): void {
  if (document.getElementById('demo-overlay-style') !== null) return;
  const style = document.createElement('style');
  style.id = 'demo-overlay-style';
  style.textContent = STYLE;
  document.head.appendChild(style);
}

/**
 * A persistent, non-dismissible disclaimer that this is synthetic sample data — so a
 * shared demo link can never be mistaken for a real patient record. Plain DOM, outside
 * the React root, demo-build only.
 */
export function mountDemoBanner(): void {
  ensureStyle();
  const banner = document.createElement('div');
  banner.className = 'demo-banner';
  banner.setAttribute('role', 'note');
  banner.setAttribute('aria-label', 'Demo notice: synthetic sample data, not a real patient');

  const dot = document.createElement('span');
  dot.className = 'demo-warn-dot';
  dot.setAttribute('aria-hidden', 'true');
  banner.appendChild(dot);

  const text = document.createElement('span');
  text.className = 'demo-warn-text';
  text.innerHTML = '<b>Demo</b> — synthetic sample data, not a real patient';
  banner.appendChild(text);

  document.body.appendChild(banner);
}

export function mountDemoBar(): void {
  ensureStyle();

  const bar = document.createElement('div');
  bar.className = 'demo-bar';
  bar.setAttribute('role', 'group');
  bar.setAttribute('aria-label', 'Demo role switcher');

  const tag = document.createElement('span');
  tag.className = 'demo-tag';
  tag.textContent = 'Demo';
  bar.appendChild(tag);

  const role = currentRole();
  const LABELS: Record<DemoRole, string> = {
    patient: 'Patient',
    clinician: 'Clinician',
    caregiver: 'Caregiver',
  };
  (['patient', 'clinician', 'caregiver'] as DemoRole[]).forEach((r) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = LABELS[r];
    if (r === role) btn.classList.add('on');
    btn.addEventListener('click', () => {
      if (currentRole() === r) return;
      setRole(r);
      seedSession();
      // Reset the route so the reload lands on the new area's home cleanly.
      window.location.hash = '';
      window.location.reload();
    });
    bar.appendChild(btn);
  });

  document.body.appendChild(bar);
}
