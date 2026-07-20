/**
 * Visit-Ready Summary — the patient-held print/PDF handout (ADR-0045). A windowed, curated
 * re-presentation of the patient's OWN recorded data to bring to an appointment. It is
 * non-diagnostic: the disclaimer is co-located under the status hero (VisitSummaryView) and the
 * printed sheet is labelled "current record, not a complete medical record".
 *
 * Windowing: a picker over the fixed set (30/60/90/120/365); changing it refetches (the window
 * is a query param the backend validates). Printing goes through the injectable print seam
 * (printHandout) — web opens the browser print dialog against the @media print stylesheet (no
 * PDF dependency in the bundle); native is a safe no-op. The picker, print button, and
 * point-of-print disclosure are screen-only (`.no-print`) so they never land on the paper.
 */

import { useCallback, useState } from 'react';
import { getMyVisitSummary } from '../../api/endpoints';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { useApi } from '../../lib/useApi';
import { printHandout } from './printHandout';
import { VisitSummaryView } from './VisitSummaryView';
import { ALLOWED_WINDOW_DAYS, DEFAULT_WINDOW_DAYS, windowLabel } from './windows';

export function HandoutPage() {
  const [windowDays, setWindowDays] = useState<number>(DEFAULT_WINDOW_DAYS);
  const fetcher = useCallback(() => getMyVisitSummary(windowDays), [windowDays]);
  const { data: summary, error, loading } = useApi(fetcher);

  return (
    <div>
      <h1>Visit summary</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        A short summary of your own recorded data to bring to your next appointment.
      </p>

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
          Print or save as PDF
        </button>
      </div>

      {/* Disclosure honesty (ADR-0031/0045): a point-of-print, patient-choice notice. Screen-only. */}
      <p className="muted no-print handout-disclose">
        Printing makes a paper copy that leaves the app. It shows your current record, not a
        complete medical record.
      </p>

      {loading && <Loading label="Preparing your summary…" />}
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      {summary !== null && (
        <VisitSummaryView
          summary={summary}
          heroEyebrow={`${windowLabel(windowDays)} summary`}
          heroAriaLabel={`Your ${windowLabel(windowDays)} summary`}
        />
      )}
    </div>
  );
}
