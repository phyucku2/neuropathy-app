/**
 * /emr/callback — the authenticated relay for the SMART redirect (ADR-0028).
 *
 * The backend's GET /emr/callback is bearer-authenticated (deliberately — runbook
 * mismatch (d)), so the EMR's bare browser redirect cannot complete the handshake by
 * itself. The EMR redirects to THIS SPA route (same origin on web; via App Links /
 * custom scheme into the native shell), which:
 *
 *   1. validates the echoed `state` against the pending value the connect flow
 *      persisted (pendingConnect.ts) — a mismatch is refused WITHOUT calling the
 *      backend (a forged link must not get to relay anything);
 *   2. relays code+state to GET /emr/callback with the patient's bearer attached;
 *   3. shows the activated connection with "Pull labs now" / disconnect actions and
 *      a route back to Sources.
 *
 * API failures (including the emr_connect-off 409) surface the backend's `detail`
 * verbatim in a role=alert (ADR-0013 convention), with a retry-from-Sources hint.
 */

import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { messageFor } from '../../api/client';
import { completeEmrCallback, pullEmrLabs, revokeEmrConnection } from '../../api/endpoints';
import type { EmrConnectionOut, EmrPullOut } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { clearPendingConnect, loadPendingConnect } from './pendingConnect';

const BACK_TO_SOURCES_HINT =
  'Go back to Sources and start the connection again from “Health record connections”.';

function ConnectionActions({
  connection,
  onChanged,
}: {
  connection: EmrConnectionOut;
  onChanged: (connection: EmrConnectionOut) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);
  const [pull, setPull] = useState<EmrPullOut | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const pullNow = async () => {
    setBusy(true);
    setActionError(null);
    try {
      setPull(await pullEmrLabs(connection.id));
    } catch (cause) {
      setActionError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  // Two-tap confirm, mirroring the clinic ConnectionRow.
  const revoke = async () => {
    if (!confirmingRevoke) {
      setConfirmingRevoke(true);
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      onChanged(await revokeEmrConnection(connection.id));
      setPull(null);
    } catch (cause) {
      setActionError(messageFor(cause));
    } finally {
      setBusy(false);
      setConfirmingRevoke(false);
    }
  };

  return (
    <>
      {actionError !== null && <ErrorNotice>{actionError}</ErrorNotice>}
      {pull !== null && (
        <SuccessNotice>
          {pull.imported > 0
            ? `Imported ${String(pull.imported)} of ${String(pull.results.length)} lab results into your record.`
            : `Nothing new to import — all ${String(pull.results.length)} lab results are already in your record.`}
        </SuccessNotice>
      )}
      {connection.status === 'active' && (
        <>
          <button
            type="button"
            className="btn-inline"
            disabled={busy}
            onClick={() => {
              void pullNow();
            }}
          >
            {busy ? 'Working…' : 'Pull labs now'}
          </button>
          <button
            type="button"
            className="btn-inline danger"
            disabled={busy}
            onClick={() => {
              void revoke();
            }}
          >
            {confirmingRevoke ? 'Tap again to confirm' : 'Disconnect'}
          </button>
        </>
      )}
    </>
  );
}

export function EmrCallbackPage() {
  const [params] = useSearchParams();
  const code = params.get('code');
  const state = params.get('state');
  const [connection, setConnection] = useState<EmrConnectionOut | null>(null);
  const [providerLabel, setProviderLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(true);
  // The backend `state` is single-use; React 18 StrictMode double-invokes effects, so
  // the relay must fire exactly once — the second invocation would consume a 404.
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) {
      return;
    }
    startedRef.current = true;

    if (code === null || state === null) {
      setError('Your provider did not send back an authorization code.');
      setWorking(false);
      return;
    }
    const pending = loadPendingConnect();
    if (pending === null || pending.state !== state) {
      // Never relay a state this app did not start (CSRF/forgery guard) — and never
      // clear a pending handshake that might still legitimately complete.
      setError(
        'This sign-in response doesn’t match a connection this app started, so it was not accepted.',
      );
      setWorking(false);
      return;
    }
    setProviderLabel(pending.providerName);
    completeEmrCallback(state, code)
      .then((record) => {
        clearPendingConnect();
        setConnection(record);
        setWorking(false);
      })
      .catch((cause: unknown) => {
        // The handshake is one-shot either way (the backend state is single-use);
        // retrying means starting over from Sources.
        clearPendingConnect();
        // The backend's detail verbatim — e.g. the emr_connect-off 409 (ADR-0013).
        setError(messageFor(cause));
        setWorking(false);
      });
  }, [code, state]);

  return (
    <div>
      <h1>Health record connection</h1>
      {working && (
        <Loading label={`Finishing your ${providerLabel ?? 'health record'} connection…`} />
      )}
      {error !== null && (
        <>
          <ErrorNotice>{error}</ErrorNotice>
          <p className="muted">{BACK_TO_SOURCES_HINT}</p>
        </>
      )}
      {connection !== null && (
        <>
          <div className="card">
            <div className="src">
              <span
                className="ic"
                style={{ background: 'var(--color-brand-sky)' }}
                aria-hidden="true"
              >
                🏥
              </span>
              <div className="info">
                <b>{connection.provider_name ?? connection.fhir_base}</b>
                <small>
                  {connection.status === 'active'
                    ? 'Connected — you can pull your labs now or anytime'
                    : 'Disconnected — no data flows from this record'}
                </small>
              </div>
              {connection.status === 'active' ? (
                <span className="pill on">Connected</span>
              ) : (
                <span className="pill off">Disconnected</span>
              )}
            </div>
            <ConnectionActions connection={connection} onChanged={setConnection} />
          </div>
        </>
      )}
      {!working && (
        <p className="muted centered">
          <Link to="/settings">Back to Sources</Link>
        </p>
      )}
    </div>
  );
}
