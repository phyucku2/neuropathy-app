/**
 * Patient detail — the clinician's per-patient view (mockup main pane), four
 * views behind one picker:
 *  - Trajectory: the SAME deterministic hero + signals the patient sees
 *    (shared components/TrajectoryView; the backend never narrates here,
 *    ADR-0012) with the non-diagnostic disclaimer.
 *  - Trend table: cross-source latest/delta/judged-direction rows.
 *  - Observations: the paginated raw records.
 *  - Features: clinician toggle authority with order-style renewal (ADR-0013).
 *
 * 404-over-403 (ADR-0012): the panel is THE list of patients this clinic may
 * read, and every /clinic/patients/{id}/* fetch answers 404 for anything else
 * — both paths render the neutral PatientNotFound screen. A 404 from ANY tab
 * (e.g. mid-session consent revocation) collapses the WHOLE detail view —
 * the name/consent header must never sit above a "not found" body.
 */

import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getClinicPatientTrajectory, getPanel } from '../../api/endpoints';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { SignalRow, TrajectoryHero } from '../../components/TrajectoryView';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';
import { CapabilityOrders } from './CapabilityOrders';
import { NonDiagnosticNote } from './NonDiagnosticNote';
import { ObservationsTable } from './ObservationsTable';
import { PatientNotFound } from './PatientNotFound';
import { PatientVisitSummary } from './PatientVisitSummary';
import { TrendTable } from './TrendTable';

type TabKey = 'trajectory' | 'summary' | 'trend-table' | 'observations' | 'features';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'trajectory', label: 'Trajectory' },
  { key: 'summary', label: 'Summary' },
  { key: 'trend-table', label: 'Trend table' },
  { key: 'observations', label: 'Observations' },
  { key: 'features', label: 'Features' },
];

function TrajectoryTab({
  patientId,
  displayName,
  onNotFound,
}: {
  patientId: string;
  displayName: string;
  onNotFound?: () => void;
}) {
  const fetcher = useCallback(() => getClinicPatientTrajectory(patientId), [patientId]);
  const { data: trajectory, error, errorStatus, loading } = useApi(fetcher);

  useEffect(() => {
    if (errorStatus === 404) {
      onNotFound?.();
    }
  }, [errorStatus, onNotFound]);

  if (loading) {
    return <Loading label="Computing the trend…" />;
  }
  if (errorStatus === 404) {
    return <PatientNotFound />;
  }
  if (error !== null || trajectory === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  return (
    <div>
      <TrajectoryHero
        trajectory={trajectory}
        eyebrow="30 Day Score"
        ariaLabel={`30 day score for ${displayName}`}
      />
      <NonDiagnosticNote />
      {trajectory.signals.length > 0 && (
        <div className="card">
          <div className="eyebrow">What&apos;s driving it</div>
          {trajectory.signals.map((signal) => (
            <SignalRow key={`${signal.source}:${signal.code}`} signal={signal} />
          ))}
        </div>
      )}
      {trajectory.data_gaps.length > 0 && (
        <div className="card">
          <div className="eyebrow">Data gaps</div>
          <ul className="muted" style={{ margin: 0, paddingLeft: 20 }}>
            {trajectory.data_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function PatientDetailPage() {
  const { patientId = '' } = useParams();
  const { data: panel, error, loading } = useApi(getPanel);
  const [tab, setTab] = useState<TabKey>('trajectory');
  // A 404 from any tab fetch (consent revoked mid-session) collapses the whole
  // view — no name, consent date, or tab chips above a "not found" body.
  const [patientGone, setPatientGone] = useState(false);
  const handleNotFound = useCallback(() => {
    setPatientGone(true);
  }, []);

  if (patientGone) {
    return <PatientNotFound />;
  }
  if (loading) {
    return <Loading label="Loading patient…" />;
  }
  if (error !== null || panel === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  const entry = panel.patients.find((patient) => patient.patient_id === patientId);
  if (entry === undefined) {
    // Not on the panel = the backend would answer 404 anyway; same neutral screen.
    return <PatientNotFound />;
  }

  return (
    <div>
      <p style={{ margin: '0 0 8px' }}>
        <Link className="link" to="/clinic">
          ← Back to panel
        </Link>
      </p>
      <h1>{entry.display_name}</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Consented {formatDayYear(Date.parse(entry.consent_granted_at))}
      </p>
      <div className="metric-picker" role="group" aria-label="Patient views">
        {TABS.map((entryTab) => (
          <button
            key={entryTab.key}
            type="button"
            className="metric-chip"
            aria-pressed={entryTab.key === tab}
            onClick={() => {
              setTab(entryTab.key);
            }}
          >
            {entryTab.label}
          </button>
        ))}
      </div>
      {tab === 'trajectory' && (
        <TrajectoryTab
          patientId={patientId}
          displayName={entry.display_name}
          onNotFound={handleNotFound}
        />
      )}
      {tab === 'summary' && (
        <PatientVisitSummary
          patientId={patientId}
          displayName={entry.display_name}
          onNotFound={handleNotFound}
        />
      )}
      {tab === 'trend-table' && <TrendTable patientId={patientId} onNotFound={handleNotFound} />}
      {tab === 'observations' && (
        <ObservationsTable patientId={patientId} onNotFound={handleNotFound} />
      )}
      {tab === 'features' && <CapabilityOrders patientId={patientId} onNotFound={handleNotFound} />}
    </div>
  );
}
