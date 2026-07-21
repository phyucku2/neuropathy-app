/**
 * Caregiver home (ADR-0047 Phase A): pick a shared patient (when there are several)
 * and see their wellness trend — the SAME deterministic TrajectoryHero the patient
 * and clinician see (never the AI narrative), with the non-diagnostic note
 * co-located. Full-scope links additionally offer the read-only Visit-Ready Summary.
 *
 * The empty state is the honest double-opt-in story: after entering a code the
 * request WAITS for the patient's approval — nothing is visible until they say yes.
 * A revoked link simply disappears from the list (and any in-flight read answers
 * 404), so the caregiver lands back on the same neutral state: no reason, no
 * existence hint (the server's non-enumeration posture). The persistent 911 banner
 * is rendered by the caregiver AppShell above this page.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getCaregiverPatients, getCaregiverPatientTrajectory } from '../../api/endpoints';
import type { CaregiverPatientOut } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { SignalRow, TrajectoryHero } from '../../components/TrajectoryView';
import { useApi } from '../../lib/useApi';
import { ClaimCodeCard } from './ClaimCodeCard';

/** Neutral not-available state (404-over-403): no reason is ever given — the patient
 *  controls sharing, and a revoked or missing record must look nonexistent. */
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

function PatientTrendSection({ patient }: { patient: CaregiverPatientOut }) {
  const fetcher = useCallback(
    () => getCaregiverPatientTrajectory(patient.patient_id),
    [patient.patient_id],
  );
  const { data: trajectory, error, errorStatus, loading } = useApi(fetcher);

  if (loading) {
    return <Loading label="Loading their trend…" />;
  }
  if (errorStatus === 404) {
    // Revoked (or gone) between the list and this read — the neutral state.
    return <NotAvailableCard />;
  }
  if (error !== null || trajectory === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  return (
    <div>
      <TrajectoryHero
        trajectory={trajectory}
        eyebrow="30 Day Score"
        ariaLabel={`30 day score for ${patient.display_name}`}
      />
      {/* Non-diagnostic + non-monitoring framing, CO-LOCATED with the direction
          (CLAUDE.md house rules): every surface showing a trend carries it beside it. */}
      <p className="disclaimer" role="note">
        This is a wellness trend of {patient.display_name}&apos;s own recorded data — not a
        diagnosis, and not live monitoring. It updates when they add data.
      </p>
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
      {patient.scope === 'full' && (
        <Link className="btn ghost" to={`/caregiver/patients/${patient.patient_id}/summary`}>
          See their Visit-Ready Summary
        </Link>
      )}
    </div>
  );
}

export function CaregiverHomePage() {
  const { data, error, loading, reload } = useApi(getCaregiverPatients);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const patients = useMemo(() => data?.patients ?? [], [data]);
  // Keep the selection valid against the CURRENT list (a revoked patient vanishes).
  useEffect(() => {
    if (patients.length > 0 && !patients.some((p) => p.patient_id === selectedId)) {
      setSelectedId(patients[0]?.patient_id ?? null);
    }
  }, [patients, selectedId]);

  // Full-page loading only on the FIRST fetch: a reload (e.g. right after a claim)
  // keeps the current screen — and the claim card's fixed waiting sentence — mounted.
  if (loading && data === null) {
    return <Loading label="Loading…" />;
  }
  if (error !== null || data === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  const selected = patients.find((p) => p.patient_id === selectedId) ?? patients[0] ?? null;

  return (
    <div>
      <h1>How they&apos;re doing</h1>
      {/* Entry point to the Alerts feed (ADR-0047 B1) — the caregiver area has no tab bar,
          so the feed hangs off a link here. Shown whenever at least one person shares. */}
      {patients.length > 0 && (
        <Link className="btn ghost" to="/caregiver/alerts">
          See your updates
        </Link>
      )}
      {patients.length === 0 && (
        <>
          <section className="card" aria-labelledby="waiting-heading">
            <div className="eyebrow" id="waiting-heading">
              Waiting for approval
            </div>
            <h2>No one is sharing with you yet</h2>
            <p className="muted" style={{ marginTop: 0 }}>
              If you&apos;ve already sent a request with an invite code, it&apos;s waiting for their
              approval — nothing is visible until they say yes. Once they approve, their wellness
              trend appears here.
            </p>
          </section>
          <ClaimCodeCard onClaimed={reload} />
        </>
      )}
      {patients.length > 1 && (
        <div className="metric-picker" role="group" aria-label="Choose a person">
          {patients.map((patient) => (
            <button
              key={patient.patient_id}
              type="button"
              className="metric-chip"
              aria-pressed={patient.patient_id === selected?.patient_id}
              onClick={() => {
                setSelectedId(patient.patient_id);
              }}
            >
              {patient.display_name}
            </button>
          ))}
        </div>
      )}
      {selected !== null && (
        <>
          <p className="muted" style={{ marginTop: 0 }}>
            {selected.display_name} is sharing{' '}
            {selected.scope === 'full' ? 'their trend and visit summary' : 'their trend'} with you.
            They can change or stop this at any time.
          </p>
          <PatientTrendSection key={selected.patient_id} patient={selected} />
          <ClaimCodeCard onClaimed={reload} />
        </>
      )}
    </div>
  );
}
