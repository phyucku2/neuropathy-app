/**
 * Danger zone — permanent account & data deletion (ADR-0027).
 *
 * "Delete my account" expands to a deliberately heavy flow: the password must be
 * re-typed (the backend re-verifies it — a stolen session alone cannot destroy an
 * account), a checkbox acknowledges that ALL health data is permanently deleted,
 * and the final button is the same two-tap confirm pattern as ConnectionRow's
 * disconnect. On success the session is cleared and the user lands on the login
 * screen with a transient confirmation (router state — no new route). A wrong
 * password shows the API's detail verbatim in a role=alert; while the request is
 * pending every control is disabled.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, messageFor } from '../../api/client';
import { deleteAccount } from '../../api/endpoints';
import { useAuth } from '../../auth/AuthContext';
import { ErrorNotice } from '../../components/StatusMessages';

export function DeleteAccountCard() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = password.length > 0 && acknowledged;

  const onDelete = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setPending(true);
    setError(null);
    try {
      await deleteAccount(password);
      // The account is gone: drop the dead session and land on the login screen,
      // carrying a transient "deleted" confirmation via router state.
      logout();
      navigate('/login', { replace: true, state: { accountDeleted: true } });
    } catch (cause) {
      // The 403 wrong-password detail is shown verbatim (role=alert).
      setError(cause instanceof ApiError ? cause.detail : messageFor(cause));
      setPending(false);
      setConfirming(false);
    }
  };

  return (
    <>
      <h2>Danger zone</h2>
      <div className="card">
        {!open ? (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Permanently delete your account and all of your health data.
            </p>
            <button
              type="button"
              className="btn-inline danger"
              onClick={() => {
                setOpen(true);
              }}
            >
              Delete my account
            </button>
          </>
        ) : (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              This permanently deletes your account, your connections, and every piece of your
              health data. It cannot be undone.
            </p>
            {error !== null && <ErrorNotice>{error}</ErrorNotice>}
            <div className="field">
              <label htmlFor="delete-password">Confirm your password</label>
              <input
                id="delete-password"
                type="password"
                autoComplete="current-password"
                disabled={pending}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
              />
            </div>
            <div className="field">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  disabled={pending}
                  checked={acknowledged}
                  onChange={(event) => {
                    setAcknowledged(event.target.checked);
                  }}
                />
                I understand my account and all my health data will be permanently deleted.
              </label>
            </div>
            <button
              type="button"
              className="btn-inline danger"
              disabled={pending || !ready}
              onClick={() => {
                void onDelete();
              }}
            >
              {pending
                ? 'Deleting…'
                : confirming
                  ? 'Tap again to permanently delete'
                  : 'Delete my account and data'}
            </button>
            <button
              type="button"
              className="btn-inline"
              disabled={pending}
              onClick={() => {
                setOpen(false);
                setPassword('');
                setAcknowledged(false);
                setConfirming(false);
                setError(null);
              }}
            >
              Keep my account
            </button>
          </>
        )}
      </div>
    </>
  );
}
