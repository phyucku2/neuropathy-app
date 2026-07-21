/**
 * Caregiver Alerts feed (ADR-0047 Phase B1): the in-app list of non-urgent wellness
 * nudges for the people this caregiver follows, each acknowledgeable in one tap.
 *
 * The feed is COMPUTE-ON-READ and scope + preference gated on the server: a trends-only
 * caregiver never sees a med/note alert (not even its existence), and a type the patient
 * hasn't opted into never appears. The bodies are fixed, non-diagnostic template copy
 * that already carry the "not for emergencies, call 911" framing; on top of the shell's
 * persistent 911 banner we co-locate the same non-urgent note (role="note") right beside
 * the list, per the house rule that the framing rides WITH the data on every surface.
 *
 * Acknowledging is idempotent on the server (a double-ack is a quiet success); the UI
 * marks the row done optimistically and rolls back with a verbatim message on failure.
 * 60+ plain language, AA contrast (reuses the verified .disclaimer / .pill / .card
 * treatments — no new color pairs), non-diagnostic throughout.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { messageFor } from '../../api/client';
import { acknowledgeCaregiverAlert, getCaregiverAlerts } from '../../api/endpoints';
import type { CaregiverAlertOut } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';
import { ALERT_TYPE_META } from './alertMeta';

function AlertRow({
  alert,
  acknowledged,
  onAcknowledged,
  onError,
}: {
  alert: CaregiverAlertOut;
  acknowledged: boolean;
  onAcknowledged: (id: string) => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const meta = ALERT_TYPE_META[alert.alert_type];

  const acknowledge = async () => {
    setBusy(true);
    onError('');
    try {
      // Idempotent on the server — a double-ack is a quiet 204. We mark it done on success.
      await acknowledgeCaregiverAlert(alert.id);
      onAcknowledged(alert.id);
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" aria-label={meta.label}>
      <div className="src" style={{ padding: 0 }}>
        <span className="ic" style={{ background: meta.color }} aria-hidden="true">
          {meta.glyph}
        </span>
        <div className="info">
          <b>{alert.title}</b>
          <small>
            About {alert.patient_display_name} · {formatDayYear(Date.parse(alert.created_at))}
          </small>
        </div>
        <span className={acknowledged ? 'pill off' : 'pill warn'}>
          {acknowledged ? 'Seen' : 'New'}
        </span>
      </div>
      <p className="muted" style={{ margin: '10px 0 0' }}>
        {alert.body}
      </p>
      {!acknowledged && (
        <button
          type="button"
          className="btn-inline"
          disabled={busy}
          onClick={() => {
            void acknowledge();
          }}
        >
          {busy ? 'Saving…' : 'Got it'}
        </button>
      )}
    </div>
  );
}

export function CaregiverAlertsPage() {
  const { data, error, loading } = useApi(getCaregiverAlerts);
  // Optimistic acknowledged set, merged over the server's own acknowledged_at.
  const [acked, setAcked] = useState<Set<string>>(new Set());
  const [actionError, setActionError] = useState<string | null>(null);

  if (loading && data === null) {
    return <Loading label="Loading updates…" />;
  }
  if (error !== null || data === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  const alerts = data.alerts;

  return (
    <div>
      <p style={{ margin: '0 0 8px' }}>
        <Link className="link" to="/caregiver">
          ← Back
        </Link>
      </p>
      <h1>Updates</h1>
      {/* The non-urgent framing rides WITH the data (ADR-0047), co-located beside the
          list in addition to the shell's persistent 911 banner. */}
      <p className="disclaimer" role="note">
        These are occasional, non-urgent updates about the people you follow — not a
        diagnosis, and not live monitoring. {data.emergency_notice}
      </p>
      {actionError !== null && actionError !== '' && <ErrorNotice>{actionError}</ErrorNotice>}
      {alerts.length === 0 ? (
        <section className="card" aria-labelledby="no-updates-heading">
          <div className="eyebrow" id="no-updates-heading">
            All caught up
          </div>
          <h2>No updates right now</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            When someone you follow chooses to share updates, they&apos;ll appear here. Each
            person decides which updates to turn on, and can change that at any time.
          </p>
        </section>
      ) : (
        alerts.map((alert) => (
          <AlertRow
            key={alert.id}
            alert={alert}
            acknowledged={alert.acknowledged_at !== null || acked.has(alert.id)}
            onAcknowledged={(id) => {
              setAcked((current) => new Set(current).add(id));
            }}
            onError={setActionError}
          />
        ))
      )}
    </div>
  );
}
