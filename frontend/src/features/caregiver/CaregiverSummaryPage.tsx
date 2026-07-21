/**
 * Read-only Visit-Ready Summary for a FULL-scope caregiver (ADR-0047) — the SAME
 * `VisitSummary` assembly and shared VisitSummaryView the patient prints and the
 * clinician reads (ADR-0045), so the surfaces can never drift. Deterministic only;
 * EMR notes render as metadata-only rows exactly as elsewhere.
 *
 * A trends-scope caller — or a revoked/unknown patient — gets a 404 from the server
 * that is indistinguishable from nonexistent, rendered here as the same neutral
 * not-available state as the home screen (no reason, no existence hint). The
 * persistent 911 banner is rendered by the caregiver AppShell.
 */

import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getCaregiverPatients, getCaregiverPatientVisitSummary } from '../../api/endpoints';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { useApi } from '../../lib/useApi';
import { VisitSummaryView } from '../handout/VisitSummaryView';
import { ALLOWED_WINDOW_DAYS, DEFAULT_WINDOW_DAYS, windowLabel } from '../handout/windows';

function NotAvailableCard() {
  return (
    <div className="card">
      <div className="eyebrow">Not available</div>
      <h2>This isn&apos;t available right now</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        The person you follow controls what is shared, and sharing can change at any time. If you
        expected to see something here, ask them directly.
      </p>
    </div>
  );
}

function SummaryBody({ patientId, displayName }: { patientId: string; displayName: string }) {
  const [windowDays, setWindowDays] = useState<number>(DEFAULT_WINDOW_DAYS);
  const fetcher = useCallback(
    () => getCaregiverPatientVisitSummary(patientId, windowDays),
    [patientId, windowDays],
  );
  const { data: summary, error, errorStatus, loading } = useApi(fetcher);

  if (errorStatus === 404) {
    // Insufficient scope, revoked, or unknown — all indistinguishable; same neutral state.
    return <NotAvailableCard />;
  }

  return (
    <div>
      <div className="metric-picker" role="group" aria-label="Choose a time window">
        {ALLOWED_WINDOW_DAYS.map((days) => (
          <button
            key={days}
            type="button"
            className="metric-chip"
            aria-pressed={days === windowDays}
            onClick={() => {
              setWindowDays(days);
            }}
          >
            {windowLabel(days)}
          </button>
        ))}
      </div>
      {loading && <Loading label="Preparing the summary…" />}
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      {/* Labelled from the payload's own window — never the picker state. */}
      {!loading && summary !== null && (
        <VisitSummaryView
          summary={summary}
          heroEyebrow={`${windowLabel(summary.window_days)} summary`}
          heroAriaLabel={`${windowLabel(summary.window_days)} summary for ${displayName}`}
        />
      )}
    </div>
  );
}

export function CaregiverSummaryPage() {
  const { patientId = '' } = useParams();
  const { data, error, loading } = useApi(getCaregiverPatients);

  if (loading) {
    return <Loading label="Loading…" />;
  }
  if (error !== null || data === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  const entry = data.patients.find((patient) => patient.patient_id === patientId);

  return (
    <div>
      <p style={{ margin: '0 0 8px' }}>
        <Link className="link" to="/caregiver">
          ← Back
        </Link>
      </p>
      {/* Not shared (or not at full scope) = the server would answer 404 anyway; the
          same neutral screen, before any read is even attempted. */}
      {entry === undefined || entry.scope !== 'full' ? (
        <NotAvailableCard />
      ) : (
        <>
          <h1>{entry.display_name}&apos;s Visit-Ready Summary</h1>
          <p className="muted" style={{ marginTop: 0 }}>
            A read-only view of what {entry.display_name} recorded — the same summary they can bring
            to a visit. Each item shows its source and date.
          </p>
          <SummaryBody patientId={entry.patient_id} displayName={entry.display_name} />
        </>
      )}
    </div>
  );
}
