/**
 * Sources — the mockup's toggle rows (screen 2) over GET/PUT /capabilities.
 * enforced=false rows render read-only ("coming soon"); PUT is optimistic
 * with rollback on failure, and a 409's server message (e.g. clinically
 * managed) is surfaced verbatim (ADR-0013). Below: clinic connections with
 * consent grant/revoke, then EMR health-record connections (ADR-0028).
 */

import { useEffect, useState } from 'react';
import { ApiError, messageFor } from '../../api/client';
import { getCapabilities, getConnections, putCapability } from '../../api/endpoints';
import type { CapabilityStateOut } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';
import { CaregiverAlertPreferencesCard } from './CaregiverAlertPreferencesCard';
import { CaregiverShareCard } from './CaregiverShareCard';
import { ConnectionRow } from './ConnectionRow';
import { DeleteAccountCard } from './DeleteAccountCard';
import { DownloadDataCard } from './DownloadDataCard';
import { EmrConnectCard } from './EmrConnectCard';
import { RecordsLinkCard } from './RecordsLinkCard';
import { ReminderCard } from './ReminderCard';
import { VisitSummaryLinkCard } from './VisitSummaryLinkCard';

const CAPABILITY_ICONS: Record<string, { glyph: string; color: string }> = {
  ingest_biomech: { glyph: '◔', color: 'var(--color-brand-blue)' },
  ingest_labs: { glyph: '⚗', color: 'var(--color-status-warning)' },
  ingest_adl: { glyph: '☑', color: 'var(--color-action-green)' },
  ingest_symptoms: { glyph: '✚', color: 'var(--color-status-warning)' },
  ingest_wearable: { glyph: '📲', color: 'var(--color-brand-sky)' },
  emr_connect: { glyph: '🏥', color: 'var(--color-brand-sky)' },
  ai_narrative: { glyph: '✦', color: 'var(--color-brand-navy)' },
  share_with_clinic: { glyph: '👪', color: 'var(--color-text-secondary)' },
  log_food: { glyph: '🍎', color: 'var(--color-action-green)' },
};

function CapabilityRow({
  capability,
  onToggle,
  disabled,
}: {
  capability: CapabilityStateOut;
  onToggle: (capability: CapabilityStateOut) => void;
  disabled: boolean;
}) {
  const icon = CAPABILITY_ICONS[capability.key] ?? {
    glyph: '⚙',
    color: 'var(--color-status-neutral)',
  };
  const managedByClinic = capability.managed_by === 'clinic';
  return (
    <div className="src">
      <span className="ic" style={{ background: icon.color }} aria-hidden="true">
        {icon.glyph}
      </span>
      <div className="info">
        <b>{capability.name}</b>
        <small>
          {!capability.enforced
            ? 'Coming soon'
            : managedByClinic
              ? // A clinician-set expiry (the only way expiry exists) renders
                // WITH the managed-by label, never hidden behind it.
                capability.expires_at !== null
                ? `Managed by your clinic · until ${formatDayYear(Date.parse(capability.expires_at))}`
                : 'Managed by your clinic'
              : capability.expires_at !== null
                ? `Until ${formatDayYear(Date.parse(capability.expires_at))}`
                : capability.active
                  ? 'On'
                  : 'Off · hidden and paused in your trend'}
        </small>
      </div>
      {capability.enforced ? (
        <button
          type="button"
          role="switch"
          aria-checked={capability.active}
          aria-label={capability.name}
          className="tg"
          disabled={disabled}
          onClick={() => {
            onToggle(capability);
          }}
        />
      ) : (
        <span className="pill off">Coming soon</span>
      )}
    </div>
  );
}

function CapabilitiesCard() {
  const { data, error, loading } = useApi(getCapabilities);
  const [rows, setRows] = useState<CapabilityStateOut[] | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  useEffect(() => {
    if (data !== null) {
      setRows(data.capabilities);
    }
  }, [data]);

  const toggle = async (capability: CapabilityStateOut) => {
    const next = !capability.active;
    setSaveError(null);
    setSavingKey(capability.key);
    // Optimistic flip — rolled back if the server refuses (ADR-0013: the
    // server's judgment is the authority; the client toggle is a UI hint).
    setRows(
      (current) =>
        current?.map((row) => (row.key === capability.key ? { ...row, active: next } : row)) ??
        null,
    );
    try {
      const confirmed = await putCapability(capability.key, next);
      setRows(
        (current) => current?.map((row) => (row.key === capability.key ? confirmed : row)) ?? null,
      );
    } catch (cause) {
      setRows(
        (current) => current?.map((row) => (row.key === capability.key ? capability : row)) ?? null,
      );
      // A 409 carries the server's own explanation (e.g. clinically managed) —
      // surfaced verbatim.
      setSaveError(cause instanceof ApiError ? cause.detail : messageFor(cause));
    } finally {
      setSavingKey(null);
    }
  };

  if (loading && rows === null) {
    return <Loading label="Loading your sources…" />;
  }
  if (error !== null || rows === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  return (
    <>
      {saveError !== null && <ErrorNotice>{saveError}</ErrorNotice>}
      <div className="card">
        {rows.map((capability) => (
          <CapabilityRow
            key={capability.key}
            capability={capability}
            disabled={savingKey !== null}
            onToggle={(row) => {
              void toggle(row);
            }}
          />
        ))}
      </div>
      <p className="muted centered">
        Turning a source off hides it and pauses its use in your trend.
      </p>
    </>
  );
}

function ConnectionsCard() {
  const { data: connections, error, loading, reload } = useApi(getConnections);

  return (
    <>
      <h2>Your clinic</h2>
      <div className="card">
        {loading && <Loading label="Loading connections…" />}
        {error !== null && <ErrorNotice>{error}</ErrorNotice>}
        {connections !== null && connections.length === 0 && (
          <p className="muted" style={{ margin: 0 }}>
            No clinic connections. You&apos;re self-managing — your data is yours alone until you
            approve a connection.
          </p>
        )}
        {connections !== null &&
          connections.map((connection) => (
            <ConnectionRow key={connection.id} connection={connection} onChanged={reload} />
          ))}
      </div>
    </>
  );
}

export function SettingsPage() {
  return (
    <div>
      <h1>Your data sources</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Turn on what fits you. Everything is optional — your app, your way.
      </p>
      <CapabilitiesCard />
      {/* Daily check-in reminder (ADR-0029) sits with the source toggles — a
          preference, deliberately outside the danger zone below. Native-only;
          web renders the honest fallback. */}
      <ReminderCard />
      <ConnectionsCard />
      {/* Caregiver sharing (ADR-0047) sits beside the clinic connection — the same
          patient-held, revocable consent primitive with a different grantee. */}
      <CaregiverShareCard />
      {/* Per-type caregiver-alert opt-ins (ADR-0047 B1) — a sibling to the share card,
          DEFAULT OFF: nothing is sent to a caregiver until the patient turns it on. */}
      <CaregiverAlertPreferencesCard />
      {/* EMR connect (ADR-0028) sits with the clinic connections — a data-source
          concern, deliberately outside the danger zone below. */}
      <EmrConnectCard />
      {/* Your Records (read-only, display-only) is reached from here — beside the EMR
          connection card, since the connection is what brings the record in. Not a
          sixth nav tab (ADR-0039: five is the accessible max). */}
      <RecordsLinkCard />
      {/* Visit-Ready Summary (ADR-0045): the printable appointment handout, grouped with the
          other take-your-data-out affordances, above the danger zone. */}
      <VisitSummaryLinkCard />
      {/* Right-of-access export (ADR-0031): the safe counterpart to deletion, placed
          ABOVE the danger zone and clearly separated from it. */}
      <DownloadDataCard />
      <DeleteAccountCard />
    </div>
  );
}
