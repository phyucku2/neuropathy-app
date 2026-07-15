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

export function LoginPage() {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
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
      await login(email, password);
      navigate('/', { replace: true });
    } catch (cause) {
      setError(friendlyLoginError(cause));
      setSubmitting(false);
    }
  };

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
      </div>
      <p className="muted centered">Your data stays private until you approve a connection.</p>
    </div>
  );
}
