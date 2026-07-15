/**
 * Demo entry point — installs the in-browser fetch mock + seeds a restored session,
 * then renders the REAL <App/> exactly like src/main.tsx (same providers, styles,
 * and self-hosted fonts).
 *
 * HashRouter (not BrowserRouter) is used so the single hosted HTML file survives a
 * refresh at any path and any hosting sub-path — every in-app route lives under `#/`.
 * The app's route paths ("/", "trends", "check-in", "add", "settings", "clinic",
 * "clinic/patients/:id") resolve identically under the hash.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';

// Self-hosted fonts (SIL OFL 1.1) — inlined as data URIs in the single-file build.
import '@fontsource/poppins/500.css';
import '@fontsource/poppins/600.css';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';

import '../../src/styles/tokens.css';
import '../../src/styles/app.css';

import { App } from '../../src/App';
import { AuthProvider } from '../../src/auth/AuthContext';
import { installDemoMock, seedSession } from './mock';
import { mountDemoBar } from './demoBar';

// Order matters: the mock must own window.fetch and the session must be seeded
// BEFORE React mounts and the AuthProvider fires its restore effect.
installDemoMock();
seedSession();

const container = document.getElementById('root');
if (container === null) {
  throw new Error('Missing #root element');
}

createRoot(container).render(
  <StrictMode>
    <HashRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </HashRouter>
  </StrictMode>,
);

mountDemoBar();
