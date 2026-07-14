/**
 * Auth context: session state + login/register/logout.
 *
 * On mount a stored refresh token restores the session via GET /auth/me — the client's
 * refresh-on-401 retry mints the access token. On WEB the token lives in sessionStorage
 * (read synchronously, ADR-0015). On NATIVE it lives in the Keystore (ADR-0024): the
 * provider first primes the token from the secure store and requires a biometric unlock
 * before the restore may proceed, so a persisted session is never revealed silently.
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
import type { MeOut, TokenOut } from '../api/types';
import { resolveNativeRestore } from './nativeRestore';
import { isNativePlatform } from './platform';
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
  const native = isNativePlatform();
  const [status, setStatus] = useState<AuthStatus>(() =>
    // Web decides synchronously from sessionStorage (unchanged). Native cannot read the
    // Keystore synchronously, so it starts in `restoring` and the preamble effect resolves it.
    native ? 'restoring' : getRefreshToken() === null ? 'anonymous' : 'restoring',
  );
  // Web is ready to restore immediately; native must prime the Keystore + pass biometric first.
  const [primed, setPrimed] = useState<boolean>(!native);
  const [user, setUser] = useState<MeOut | null>(null);

  useEffect(() => {
    return onSessionExpired(() => {
      setUser(null);
      setStatus('anonymous');
    });
  }, []);

  // Native-only preamble (runs once): prime the Keystore token and require a biometric unlock
  // (resolveNativeRestore). 'anonymous' means no token OR a failed/cancelled unlock — the token
  // is left in the Keystore for a retry next launch (a denied prompt grants no access either way;
  // only logout clears it), and staying anonymous means no authenticated request is issued, so a
  // primed token is never used. 'restore' lets the getMe() effect below run.
  useEffect(() => {
    if (!native) {
      return;
    }
    let cancelled = false;
    void resolveNativeRestore().then((decision) => {
      if (cancelled) return;
      if (decision === 'anonymous') {
        setStatus('anonymous');
      }
      setPrimed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [native]);

  useEffect(() => {
    if (status !== 'restoring' || !primed) {
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
  }, [status, primed]);

  // Tokens only stay persisted if the WHOLE sign-in sequence succeeds: if the
  // profile read fails, the stored session (memory + durable store) is cleared
  // before rethrowing, so a "failed" sign-in never leaves a live refresh token
  // behind (kiosk / shared-machine risk).
  const establishSession = useCallback(async (tokens: TokenOut) => {
    await storeSession(tokens);
    let me: MeOut;
    try {
      me = await getMe();
    } catch (cause) {
      clearSession();
      throw cause;
    }
    setUser(me);
    setStatus('authenticated');
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      await establishSession(await apiLogin({ email, password }));
    },
    [establishSession],
  );

  const register = useCallback(
    async (displayName: string, email: string, password: string) => {
      await establishSession(await apiRegister({ email, password, display_name: displayName }));
    },
    [establishSession],
  );

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
