/**
 * Clinician-side Visit-Ready Summary (ADR-0045) — the SAME `VisitSummary` the patient prints,
 * rendered inside the consent-gated PatientDetailPage. Deterministic only (the backend never
 * narrates the clinician surface, ADR-0012); a 404 (consent revoked / unknown id) collapses the
 * whole detail view via `onNotFound`, matching the other tabs (never a 403 or access reason).
 *
 * A window picker (the fixed 30/60/90/120/365 set) refetches, and a print/export affordance
 * opens the browser print dialog against the shared @media print stylesheet — the same
 * VisitSummaryView the patient sees, so the two surfaces can never drift.
 */

import { useCallback, useEffect, useState } from 'react';
import { getClinicPatientVisitSummary } from '../../api/endpoints';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { printHandout } from '../handout/printHandout';
import { VisitSummaryView } from '../handout/VisitSummaryView';
import { ALLOWED_WINDOW_DAYS, DEFAULT_WINDOW_DAYS, windowLabel } from '../handout/windows';
import { useApi } from '../../lib/useApi';
import { PatientNotFound } from './PatientNotFound';

export function PatientVisitSummary({
  patientId,
  displayName,
  onNotFound,
}: {
  patientId: string;
  displayName: string;
  onNotFound?: () => void;
}) {
  const [windowDays, setWindowDays] = useState<number>(DEFAULT_WINDOW_DAYS);
  const fetcher = useCallback(
    () => getClinicPatientVisitSummary(patientId, windowDays),
    [patientId, windowDays],
  );
  const { data: summary, error, errorStatus, loading } = useApi(fetcher);

  useEffect(() => {
    if (errorStatus === 404) {
      onNotFound?.();
    }
  }, [errorStatus, onNotFound]);

  if (errorStatus === 404) {
    return <PatientNotFound />;
  }

  return (
    <div>
      <div className="handout-controls no-print">
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
        <button
          type="button"
          className="btn-inline"
          disabled={summary === null}
          onClick={() => {
            printHandout();
          }}
        >
          Print or export
        </button>
      </div>

      {loading && <Loading label="Preparing the summary…" />}
      {error !== null && errorStatus !== 404 && <ErrorNotice>{error}</ErrorNotice>}
      {summary !== null && (
        <VisitSummaryView
          summary={summary}
          heroEyebrow={`${windowLabel(windowDays)} summary`}
          heroAriaLabel={`${windowLabel(windowDays)} summary for ${displayName}`}
        />
      )}
    </div>
  );
}
