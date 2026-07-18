/** Render the whole app (router + auth) at a path, optionally signed in. */

import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import { AuthProvider } from '../auth/AuthContext';
import { storeSession } from '../auth/tokenStore';
import { markOnboardingComplete } from '../features/onboarding/onboardingState';
import { ME, TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN } from './fixtures';

export function signIn(): void {
  storeSession({ access_token: TEST_ACCESS_TOKEN, refresh_token: TEST_REFRESH_TOKEN });
}

// `onboarded` defaults TRUE: a signed-in test user is a RETURNING patient, so patient-area
// tests render their target page rather than the first-run wizard (ADR-0044). The onboarding
// test opts out with `{ onboarded: false }` to exercise the welcome gate.
export function renderApp(path = '/', { authenticated = true, onboarded = true } = {}) {
  if (authenticated) {
    signIn();
    if (onboarded) {
      markOnboardingComplete(ME.user_id);
    }
  }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
