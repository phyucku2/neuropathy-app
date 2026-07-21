import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { ErrorNotice, SuccessNotice } from '../../components/StatusMessages';

function friendlyLoginError(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "That email or password didn't match. Please try again.";
  }
  if (error instanceof ApiError) {
    return error.detail;
  }
  return "We couldn't reach the server. Check your connection and try again.";
}

/** The step-up's own wording: a 401 here means the CODE was wrong (the password already
 *  cleared), so the message must never re-blame the email/password. */
function friendlyMfaError(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "That code didn't match. Please try again.";
  }
  if (error instanceof ApiError) {
    return error.detail;
  }
  return "We couldn't reach the server. Check your connection and try again.";
}

export function LoginPage() {
  const { status, login, completeMfaLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  // TOTP step-up (§1B C6): non-null after a password success that still owes a code.
  // The pending token lives ONLY here — never in the token store — until verified.
  const [mfaPendingToken, setMfaPendingToken] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Transient confirmation after account deletion (ADR-0027): router state only —
  // no new route, and a reload or any navigation naturally clears it.
  const accountDeleted =
    (location.state as { accountDeleted?: boolean } | null)?.accountDeleted === true;

  if (status === 'authenticated') {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(email, password);
      if (result.kind === 'mfa_required') {
        setMfaPendingToken(result.mfaPendingToken);
        setPassword('');
        setSubmitting(false);
        return;
      }
      navigate('/', { replace: true });
    } catch (cause) {
      setError(friendlyLoginError(cause));
      setSubmitting(false);
    }
  };

  const onVerifyCode = async (event: FormEvent) => {
    event.preventDefault();
    if (mfaPendingToken === null) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await completeMfaLogin(mfaPendingToken, code);
      navigate('/', { replace: true });
    } catch (cause) {
      setError(friendlyMfaError(cause));
      setSubmitting(false);
    }
  };

  const backToSignIn = () => {
    // Dropping the pending token abandons the half-authenticated state entirely —
    // the next attempt starts from the password again.
    setMfaPendingToken(null);
    setCode('');
    setError(null);
  };

  if (mfaPendingToken !== null) {
    return (
      <div className="auth-frame">
        <div className="auth-mark">◍ Neuropathy</div>
        <div className="card">
          <h1>Two-step verification</h1>
          <p className="muted">Enter the 6-digit code from your authenticator app.</p>
          {error !== null && <ErrorNotice>{error}</ErrorNotice>}
          <form
            onSubmit={(event) => {
              void onVerifyCode(event);
            }}
          >
            <div className="field">
              <label htmlFor="login-mfa-code">6-digit code</label>
              <input
                id="login-mfa-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                value={code}
                onChange={(event) => {
                  setCode(event.target.value);
                }}
              />
            </div>
            <button className="btn" type="submit" disabled={submitting}>
              {submitting ? 'Verifying…' : 'Verify'}
            </button>
          </form>
          <button
            className="btn secondary"
            type="button"
            style={{ marginTop: 10 }}
            onClick={backToSignIn}
          >
            Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-frame">
      <div className="auth-mark">◍ Neuropathy</div>
      <div className="card">
        <h1>Welcome back</h1>
        <p className="muted">Sign in to see your trends.</p>
        {accountDeleted && <SuccessNotice>Your account and data were deleted.</SuccessNotice>}
        {error !== null && <ErrorNotice>{error}</ErrorNotice>}
        <form
          onSubmit={(event) => {
            void onSubmit(event);
          }}
        >
          <div className="field">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
          </div>
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="muted centered" style={{ marginTop: 14 }}>
          New here?{' '}
          <Link className="link" to="/register">
            Create an account
          </Link>
        </p>
        {/* Caregiver entry (ADR-0047): a loved one with an invite code starts here. */}
        <p className="muted centered">
          Caring for someone?{' '}
          <Link className="link" to="/caregiver/join">
            Use your invite code
          </Link>
        </p>
      </div>
      <p className="muted centered">Your data stays private until you approve a connection.</p>
      {/* Auth-less About/Privacy links (ADR-0032): reachable by a logged-out user and a
          store reviewer. The matching Settings link row is deferred (sibling surface). */}
      <p className="muted centered">
        <Link className="link" to="/about">
          About
        </Link>
        {' · '}
        <Link className="link" to="/privacy">
          Privacy
        </Link>
      </p>
    </div>
  );
}
