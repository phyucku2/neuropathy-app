/**
 * Features tab — clinician toggle authority over a consented patient's
 * capabilities, order-style (ADR-0013): a toggle plus an optional renewal
 * (expiry) date. Expiry pairs ONLY with active=true — the backend answers 422
 * otherwise and that message is surfaced verbatim. A renewal is therefore an
 * ENABLE-with-expiry order action (active: true sent explicitly), preceded by
 * a fresh read of the list so it never acts on a stale snapshot.
 * enforced=false rows are read-only ("not wired yet"): their features do not
 * consult the toggle, so offering the switch would be a false promise.
 */

import { useCallback, useEffect, useState } from 'react';
import { messageFor } from '../../api/client';
import { getClinicPatientCapabilities, putClinicPatientCapability } from '../../api/endpoints';
import type { CapabilityStateOut, ClinicianCapabilitySetIn } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';
import { PatientNotFound } from './PatientNotFound';

/**
 * A renewal date means "in force through that day": the order expires at the
 * end of the chosen calendar day, UTC (the backend requires a timezone-aware
 * timestamp).
 */
export function renewalDateToExpiresAt(date: string): string {
  return `${date}T23:59:59Z`;
}

/**
 * The renewal date input's floor: tomorrow in the clinician's LOCAL calendar.
 * A past (or same-day, already-mostly-elapsed) date would instantly
 * deactivate the order the moment it is set.
 */
export function minRenewalDate(now = new Date()): string {
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const month = String(tomorrow.getMonth() + 1).padStart(2, '0');
  const day = String(tomorrow.getDate()).padStart(2, '0');
  return `${String(tomorrow.getFullYear())}-${month}-${day}`;
}

function CapabilityOrderRow({
  capability,
  busy,
  onSave,
  onRenew,
}: {
  capability: CapabilityStateOut;
  busy: boolean;
  onSave: (key: string, body: ClinicianCapabilitySetIn) => void;
  onRenew: (key: string, expiresAt: string) => void;
}) {
  const [renewalDate, setRenewalDate] = useState('');

  if (!capability.enforced) {
    return (
      <div className="src">
        <div className="info">
          <b>{capability.name}</b>
          <small>Not wired to its feature yet — read-only until it is.</small>
        </div>
        <span className="pill off">Not wired yet</span>
      </div>
    );
  }

  return (
    <div>
      <div className="src">
        <div className="info">
          <b>{capability.name}</b>
          <small>{capability.active ? 'Active' : 'Off'}</small>
        </div>
        {capability.expires_at !== null ? (
          // A lapsed order has EXPIRED — "renews <past date>" would misstate it.
          <span className="expiry">
            {Date.parse(capability.expires_at) < Date.now() ? 'expired' : 'renews'}{' '}
            {formatDayYear(Date.parse(capability.expires_at))}
          </span>
        ) : (
          <span className="muted" aria-hidden="true">
            —
          </span>
        )}
        <button
          type="button"
          role="switch"
          aria-checked={capability.active}
          aria-label={capability.name}
          className="tg"
          disabled={busy}
          onClick={() => {
            // Toggling never carries an expiry: enabling starts an open-ended
            // order, disabling must not send expires_at (ADR-0013 422 rule).
            onSave(capability.key, { active: !capability.active });
          }}
        />
      </div>
      <div className="renew-row">
        <div className="field" style={{ marginBottom: 0, flex: 1 }}>
          <label htmlFor={`renew-${capability.key}`}>Renewal date</label>
          <input
            id={`renew-${capability.key}`}
            type="date"
            aria-label={`Renewal date for ${capability.name}`}
            min={minRenewalDate()}
            value={renewalDate}
            onChange={(event) => {
              setRenewalDate(event.target.value);
            }}
          />
        </div>
        <button
          type="button"
          className="btn-inline"
          aria-label={`Set renewal for ${capability.name}`}
          disabled={busy || renewalDate === ''}
          onClick={() => {
            onRenew(capability.key, renewalDateToExpiresAt(renewalDate));
          }}
        >
          Set renewal
        </button>
      </div>
    </div>
  );
}

export function CapabilityOrders({
  patientId,
  onNotFound,
}: {
  patientId: string;
  onNotFound?: () => void;
}) {
  const fetcher = useCallback(() => getClinicPatientCapabilities(patientId), [patientId]);
  const { data, error, errorStatus, loading } = useApi(fetcher);
  const [rows, setRows] = useState<CapabilityStateOut[] | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data !== null) {
      setRows(data.capabilities);
    }
  }, [data]);

  useEffect(() => {
    if (errorStatus === 404) {
      onNotFound?.();
    }
  }, [errorStatus, onNotFound]);

  const save = async (key: string, body: ClinicianCapabilitySetIn) => {
    setSaveError(null);
    setSaving(true);
    try {
      const confirmed = await putClinicPatientCapability(patientId, key, body);
      setRows((current) => current?.map((row) => (row.key === key ? confirmed : row)) ?? null);
    } catch (cause) {
      // 422 (expiry-without-enable) and 409 (ops-disabled) carry the backend's
      // own explanation — shown verbatim, no rewording.
      setSaveError(messageFor(cause));
    } finally {
      setSaving(false);
    }
  };

  const renew = async (key: string, expiresAt: string) => {
    setSaveError(null);
    setSaving(true);
    try {
      // Fresh read FIRST: the order may have changed since this page loaded
      // (another clinician, a lapse) — re-render current state before acting
      // on it rather than submitting from a stale snapshot.
      const fresh = await getClinicPatientCapabilities(patientId);
      setRows(fresh.capabilities);
      // ADR-0013 order-renewal semantics: a renewal IS an enable-with-expiry
      // order action, so active: true is sent explicitly. Renewing an expired
      // order (served as active=false) must succeed — sending the row's stale
      // active value would 422 every time.
      const confirmed = await putClinicPatientCapability(patientId, key, {
        active: true,
        expires_at: expiresAt,
      });
      setRows((current) => current?.map((row) => (row.key === key ? confirmed : row)) ?? null);
    } catch (cause) {
      setSaveError(messageFor(cause));
    } finally {
      setSaving(false);
    }
  };

  if (loading && rows === null) {
    return <Loading label="Loading features…" />;
  }
  if (errorStatus === 404) {
    return <PatientNotFound />;
  }
  if (error !== null || rows === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  return (
    <div className="card">
      <h2>Monitoring for this patient</h2>
      <div className="eyebrow">
        You control what&apos;s active — like an order, with a renewal date
      </div>
      {saveError !== null && <ErrorNotice>{saveError}</ErrorNotice>}
      {rows.map((capability) => (
        <CapabilityOrderRow
          key={capability.key}
          capability={capability}
          busy={saving}
          onSave={(key, body) => {
            void save(key, body);
          }}
          onRenew={(key, expiresAt) => {
            void renew(key, expiresAt);
          }}
        />
      ))}
      <p className="muted" style={{ marginBottom: 0 }}>
        Changes are logged and shown to the patient.
      </p>
    </div>
  );
}
