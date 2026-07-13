/**
 * Auth context: session state + login/register/logout. On mount, a stored
 * refresh token (sessionStorage, tab-scoped) restores the session via
 * GET /auth/me — the client's refresh-on-401 retry mints the access token.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getMe, login as apiLogin, register as apiRegister } from '../api/endpoints';
import type { MeOut } from '../api/types';
import { clearSession, getRefreshToken, onSessionExpired, storeSession } from './tokenStore';

export type AuthStatus = 'restoring' | 'authenticated' | 'anonymous';

export interface AuthValue {
  status: AuthStatus;
  user: MeOut | null;
  login: (email: string, password: string) => Promise<void>;
  register: (displayName: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() =>
    getRefreshToken() === null ? 'anonymous' : 'restoring',
  );
  const [user, setUser] = useState<MeOut | null>(null);

  useEffect(() => {
    return onSessionExpired(() => {
      setUser(null);
      setStatus('anonymous');
    });
  }, []);

  useEffect(() => {
    if (status !== 'restoring') {
      return;
    }
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) {
          setUser(me);
          setStatus('authenticated');
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearSession();
          setStatus('anonymous');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  const login = useCallback(async (email: string, password: string) => {
    storeSession(await apiLogin({ email, password }));
    setUser(await getMe());
    setStatus('authenticated');
  }, []);

  const register = useCallback(async (displayName: string, email: string, password: string) => {
    storeSession(await apiRegister({ email, password, display_name: displayName }));
    setUser(await getMe());
    setStatus('authenticated');
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo(
    () => ({ status, user, login, register, logout }),
    [status, user, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return value;
}
