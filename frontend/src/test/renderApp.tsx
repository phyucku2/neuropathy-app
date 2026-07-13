/** Render the whole app (router + auth) at a path, optionally signed in. */

import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App } from '../App';
import { AuthProvider } from '../auth/AuthContext';
import { storeSession } from '../auth/tokenStore';
import { TEST_ACCESS_TOKEN, TEST_REFRESH_TOKEN } from './fixtures';

export function signIn(): void {
  storeSession({ access_token: TEST_ACCESS_TOKEN, refresh_token: TEST_REFRESH_TOKEN });
}

export function renderApp(path = '/', { authenticated = true } = {}) {
  if (authenticated) {
    signIn();
  }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}
