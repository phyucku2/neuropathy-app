/**
 * Two-step verification enrollment (§1B C6) — the clinician/ops settings card.
 *
 * Enrollment mints a TOTP secret server-side (stored ONLY vault-encrypted) and answers
 * the otpauth:// URI + secret exactly ONCE. This card renders that one showing, requires
 * a current 6-digit code to prove the authenticator holds the secret, and then drops the
 * secret from state forever — there is no re-read endpoint, by design. Patients never
 * see this card: it lives only under the clinician area's /clinic/settings route.
 */

import { useState, type FormEvent } from 'react';
import { ApiError, messageFor } from '../../api/client';
import { confirmMfaEnrollment, enrollMfa, getMfaStatus } from '../../api/endpoints';
import type { MfaEnrollOut } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { useApi } from '../../lib/useApi';

/** A confirm 401 means the CODE was wrong — say so, never a generic auth complaint. */
function friendlyConfirmError(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "That code didn't match. Please try again.";
  }
  return messageFor(error);
}

export function MfaEnrollmentCard() {
  const { data: mfaStatus, error, loading } = useApi(getMfaStatus);
  // The one-time secret showing. Non-null only between "Set up" and a confirmed code.
  const [factor, setFactor] = useState<MfaEnrollOut | null>(null);
  const [code, setCode] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const enrolled = confirmed || (mfaStatus?.enrolled ?? false);

  const startEnrollment = async () => {
    setBusy(true);
    setActionError(null);
    try {
      setFactor(await enrollMfa());
    } catch (cause) {
      setActionError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      await confirmMfaEnrollment(code);
      setConfirmed(true);
      // Shown once: the secret leaves memory the moment the factor is live.
      setFactor(null);
      setCode('');
    } catch (cause) {
      setActionError(friendlyConfirmError(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2>Two-step verification</h2>
      <div className="card">
        {loading && <Loading label="Checking two-step verification…" />}
        {!loading && error !== null && <ErrorNotice>{error}</ErrorNotice>}
        {!loading && error === null && enrolled && (
          <p style={{ margin: 0 }}>
            <span className="pill on">On</span> Signing in requires a code from your authenticator
            app.
          </p>
        )}
        {!loading && error === null && !enrolled && factor === null && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Protect patient data with a second sign-in step: a 6-digit code from an authenticator
              app on your phone.
            </p>
            {actionError !== null && <ErrorNotice>{actionError}</ErrorNotice>}
            <button
              className="btn secondary"
              type="button"
              disabled={busy}
              onClick={() => {
                void startEnrollment();
              }}
            >
              Set up two-step verification
            </button>
          </>
        )}
        {!loading && error === null && !enrolled && factor !== null && (
          <>
            <SuccessNotice>
              Add this to your authenticator app now — it is shown only once.
            </SuccessNotice>
            <div className="field">
              <label htmlFor="mfa-otpauth-uri">Authenticator link (otpauth URI)</label>
              <input id="mfa-otpauth-uri" type="text" readOnly value={factor.otpauth_uri} />
            </div>
            <div className="field">
              <label htmlFor="mfa-secret">Secret key (manual entry)</label>
              <input id="mfa-secret" type="text" readOnly value={factor.secret} />
            </div>
            {actionError !== null && <ErrorNotice>{actionError}</ErrorNotice>}
            <form
              onSubmit={(event) => {
                void confirm(event);
              }}
            >
              <div className="field">
                <label htmlFor="mfa-confirm-code">6-digit code from your app</label>
                <input
                  id="mfa-confirm-code"
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
              <button className="btn" type="submit" disabled={busy}>
                Turn on two-step verification
              </button>
            </form>
          </>
        )}
      </div>
    </>
  );
}
