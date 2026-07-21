/**
 * Caregiver registration (ADR-0047): create a caregiver account WITH a patient's
 * invite code — self-registration exists only inside the invite-claim flow. Success
 * creates a PENDING link; the home screen then shows the honest waiting state until
 * the patient explicitly accepts (double opt-in).
 *
 * Auth-less (like /register). A dead code answers one fixed message — unknown,
 * expired, used, and cancelled are indistinguishable — shown verbatim. The 911
 * banner rides this screen too: every caregiver surface carries it (ADR-0047).
 */

import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { messageFor } from '../../api/client';
import { useAuth } from '../../auth/AuthContext';
import { EmergencyBanner } from '../../components/EmergencyBanner';
import { ErrorNotice } from '../../components/StatusMessages';

const MIN_PASSWORD_LENGTH = 8;

export function CaregiverJoinPage() {
  const { status, user, registerCaregiver } = useAuth();
  const navigate = useNavigate();
  const [code, setCode] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (status === 'authenticated') {
    // A signed-in caregiver claims further codes from their home; anyone else
    // lands back in their own area (the role guards take it from '/').
    return <Navigate to={user?.role === 'caregiver' ? '/caregiver' : '/'} replace />;
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
      await registerCaregiver(code.trim(), displayName, email, password);
      navigate('/caregiver', { replace: true });
    } catch (cause) {
      // The fixed dead-code 404, an email 409, or the claim throttle's 429 — verbatim.
      setError(messageFor(cause));
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-frame">
      <div className="auth-mark">◍ Neuropathy</div>
      <EmergencyBanner />
      <div className="card">
        <h1>Stay close to how they&apos;re doing</h1>
        <p className="muted">
          Enter the invite code your loved one shared with you and create your account. They approve
          the connection — and they stay in control of what you see.
        </p>
        {error !== null && <ErrorNotice>{error}</ErrorNotice>}
        <form
          onSubmit={(event) => {
            void onSubmit(event);
          }}
        >
          <div className="field">
            <label htmlFor="join-code">Invite code</label>
            <input
              id="join-code"
              type="text"
              autoComplete="off"
              required
              maxLength={64}
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="join-name">Your name</label>
            <input
              id="join-name"
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
            <label htmlFor="join-email">Email</label>
            <input
              id="join-email"
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
            <label htmlFor="join-password">Password</label>
            <input
              id="join-password"
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
            {submitting ? 'Creating account…' : 'Create account & send request'}
          </button>
        </form>
        <p className="muted centered" style={{ marginTop: 14 }}>
          Already have an account?{' '}
          <Link className="link" to="/login">
            Sign in
          </Link>
        </p>
      </div>
      <p className="muted centered">
        This shows a periodic wellness trend, not live monitoring, and it is never a diagnosis.
      </p>
    </div>
  );
}
