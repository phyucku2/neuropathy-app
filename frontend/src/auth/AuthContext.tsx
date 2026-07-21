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
import { ApiError } from '../api/client';
import {
  getMe,
  isMfaPending,
  login as apiLogin,
  register as apiRegister,
  registerCaregiver as apiRegisterCaregiver,
  verifyMfa,
} from '../api/endpoints';
import type { MeOut, TokenOut } from '../api/types';
import { purgeQueuedCheckInsForOtherOwners } from '../features/checkin/offlineQueue';
import { resolveNativeRestore } from './nativeRestore';
import { isNativePlatform } from './platform';
import { clearSession, getRefreshToken, onSessionExpired, storeSession } from './tokenStore';

export type AuthStatus = 'restoring' | 'authenticated' | 'anonymous';

/**
 * The outcome of a password login (§1B C6): fully signed in, or — for a clinician/ops
 * account with an enrolled authenticator — an MFA code still owed. In the pending case
 * NOTHING is stored: the short-lived mfa_pending token lives only in the login screen's
 * state until `completeMfaLogin` exchanges it (plus the code) for the real tokens.
 */
export type LoginResult =
  { kind: 'authenticated' } | { kind: 'mfa_required'; mfaPendingToken: string };

export interface AuthValue {
  status: AuthStatus;
  user: MeOut | null;
  login: (email: string, password: string) => Promise<LoginResult>;
  completeMfaLogin: (mfaPendingToken: string, code: string) => Promise<void>;
  register: (displayName: string, email: string, password: string) => Promise<void>;
  /** Caregiver self-registration (ADR-0047): only possible WITH a patient's invite code.
   *  The resulting link is pending — nothing is visible until the patient accepts. */
  registerCaregiver: (
    code: string,
    displayName: string,
    email: string,
    password: string,
  ) => Promise<void>;
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
          // The active account is confirmed: purge any OTHER account's offline
          // check-ins left on this browser — foreign health answers must not
          // persist once a different user is known to be active (ADR-0030).
          purgeQueuedCheckInsForOtherOwners(me.user_id);
          setUser(me);
          setStatus('authenticated');
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          // Only a REAL auth rejection (ApiError — the server saw and refused the
          // session; a genuine 401 expiry has already funneled through
          // notifySessionExpired) ends the session and clears storage. A NETWORK
          // failure (fetch TypeError — e.g. the app was reopened while still
          // offline) is transient: keep the stored refresh token AND the offline
          // check-in queue intact, so a later online launch restores the session
          // and flushes the captured entries instead of destroying them. Either
          // way the UI lands on /login — nothing renders as authenticated
          // without a confirmed profile.
          if (cause instanceof ApiError) {
            clearSession();
          }
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
    // Same rule as the restore path: signing in binds this browser to `me`, so any
    // other account's queued offline check-ins are purged now (ADR-0030).
    purgeQueuedCheckInsForOtherOwners(me.user_id);
    setUser(me);
    setStatus('authenticated');
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const result = await apiLogin({ email, password });
      if (isMfaPending(result)) {
        // Password success alone establishes NO session (§1B C6): no token is stored
        // until the 6-digit code clears /auth/mfa/verify. Patients never take this
        // branch — their login always answers full tokens.
        return { kind: 'mfa_required', mfaPendingToken: result.mfa_pending_token };
      }
      await establishSession(result);
      return { kind: 'authenticated' };
    },
    [establishSession],
  );

  const completeMfaLogin = useCallback(
    async (mfaPendingToken: string, code: string) => {
      await establishSession(await verifyMfa({ mfa_pending_token: mfaPendingToken, code }));
    },
    [establishSession],
  );

  const register = useCallback(
    async (displayName: string, email: string, password: string) => {
      await establishSession(await apiRegister({ email, password, display_name: displayName }));
    },
    [establishSession],
  );

  const registerCaregiver = useCallback(
    async (code: string, displayName: string, email: string, password: string) => {
      await establishSession(
        await apiRegisterCaregiver({ code, email, password, display_name: displayName }),
      );
    },
    [establishSession],
  );

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo(
    () => ({ status, user, login, completeMfaLogin, register, registerCaregiver, logout }),
    [status, user, login, completeMfaLogin, register, registerCaregiver, logout],
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
