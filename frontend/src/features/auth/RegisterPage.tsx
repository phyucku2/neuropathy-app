import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { messageFor } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { ErrorNotice } from '../../components/StatusMessages';

const MIN_PASSWORD_LENGTH = 8;

export function RegisterPage() {
  const { status, register } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated') {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Please choose a password of at least ${String(MIN_PASSWORD_LENGTH)} characters.`);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await register(displayName, email, password);
      navigate('/', { replace: true });
    } catch (cause) {
      setError(messageFor(cause));
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-frame">
      <div className="auth-mark">◍ Neuropathy</div>
      <div className="card">
        <h1>Create your account</h1>
        <p className="muted">Track your balance, labs, and daily function in one place.</p>
        {error !== null && <ErrorNotice>{error}</ErrorNotice>}
        <form
          onSubmit={(event) => {
            void onSubmit(event);
          }}
        >
          <div className="field">
            <label htmlFor="register-name">Your name</label>
            <input
              id="register-name"
              type="text"
              autoComplete="name"
              required
              maxLength={200}
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="register-email">Email</label>
            <input
              id="register-email"
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
            <label htmlFor="register-password">Password</label>
            <input
              id="register-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
            <p className="muted" style={{ marginTop: 6 }}>
              At least 8 characters. Longer is stronger.
            </p>
          </div>
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? 'Creating account…' : 'Create account'}
          </button>
        </form>
        <p className="muted centered" style={{ marginTop: 14 }}>
          Already have an account?{' '}
          <Link className="link" to="/login">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
