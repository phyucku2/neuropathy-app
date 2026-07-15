/**
 * A small, unobtrusive floating "Demo" role switcher.
 *
 * Rendered with plain DOM into its OWN node (outside the React #root) so it never
 * touches the real app tree. Two buttons — Patient / Clinician — write the role to
 * localStorage and reload; the fetch mock then returns the matching identity for
 * GET /auth/me, so the clinician panel is reachable without a login step.
 */

import { currentRole, seedSession, setRole, type DemoRole } from './mock';

const STYLE = `
.demo-bar {
  position: fixed; top: 10px; right: 10px; z-index: 2147483647;
  display: flex; align-items: center; gap: 6px;
  padding: 5px 6px 5px 10px; border-radius: 999px;
  background: rgba(17, 35, 46, 0.92); color: #eef4f5;
  font: 600 12px/1 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  box-shadow: 0 6px 20px rgba(10, 40, 50, 0.35); backdrop-filter: blur(6px);
  user-select: none;
}
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
`;

export function mountDemoBar(): void {
  const style = document.createElement('style');
  style.textContent = STYLE;
  document.head.appendChild(style);

  const bar = document.createElement('div');
  bar.className = 'demo-bar';
  bar.setAttribute('role', 'group');
  bar.setAttribute('aria-label', 'Demo role switcher');

  const tag = document.createElement('span');
  tag.className = 'demo-tag';
  tag.textContent = 'Demo';
  bar.appendChild(tag);

  const role = currentRole();
  (['patient', 'clinician'] as DemoRole[]).forEach((r) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = r === 'patient' ? 'Patient' : 'Clinician';
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
