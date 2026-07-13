/**
 * One clinic connection with its consent controls: approve a pending
 * invitation (POST /connections/{id}/consent) or disconnect an active one
 * (DELETE /connections/{id} — two-tap confirm; data flow stops immediately).
 */

import { useState } from 'react';
import { messageFor } from '../../api/client';
import { grantConsent, revokeConnection } from '../../api/endpoints';
import type { ConnectionOut } from '../../api/types';
import { ErrorNotice } from '../../components/StatusMessages';

export function ConnectionRow({
  connection,
  onChanged,
}: {
  connection: ConnectionOut;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);

  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      await grantConsent(connection.id);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    if (!confirmingRevoke) {
      setConfirmingRevoke(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await revokeConnection(connection.id);
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setBusy(false);
      setConfirmingRevoke(false);
    }
  };

  const statusPill =
    connection.status === 'active' ? (
      <span className="pill on">Connected</span>
    ) : connection.status === 'pending' ? (
      <span className="pill warn">Awaiting your approval</span>
    ) : (
      <span className="pill off">Disconnected</span>
    );

  return (
    <div>
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      <div className="src">
        <span className="ic" style={{ background: 'var(--color-brand-blue)' }} aria-hidden="true">
          🏥
        </span>
        <div className="info">
          <b>{connection.clinic_name}</b>
          <small>
            {connection.status === 'active'
              ? 'Your care team can see your trends'
              : connection.status === 'pending'
                ? 'No data flows until you approve'
                : 'Data flow stopped'}
          </small>
        </div>
        {statusPill}
      </div>
      {connection.status === 'pending' && (
        <button
          type="button"
          className="btn-inline"
          disabled={busy}
          onClick={() => {
            void approve();
          }}
        >
          {busy ? 'Approving…' : 'Approve connection'}
        </button>
      )}
      {connection.status === 'active' && (
        <button
          type="button"
          className="btn-inline danger"
          disabled={busy}
          onClick={() => {
            void revoke();
          }}
        >
          {busy ? 'Disconnecting…' : confirmingRevoke ? 'Tap again to confirm' : 'Disconnect'}
        </button>
      )}
    </div>
  );
}
