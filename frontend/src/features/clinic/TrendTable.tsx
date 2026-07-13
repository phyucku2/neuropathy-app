/**
 * Cross-source trend table (mockup "What the data shows"): one row per metric
 * across lab / check-in / BioMech sources with the latest value, the change
 * since the previous reading, and a judged direction from the shared signal
 * semantics (lib/signalMeta — the UI mirror of the backend registry).
 *
 * Judgment honesty: a metric whose polarity is unknown or in-range, or with a
 * single reading, says "not judged" — NEVER "stable". The word "stable" is a
 * clinical claim the data does not support here.
 */

import { useCallback } from 'react';
import { getClinicPatientObservations } from '../../api/endpoints';
import type { ObservationItem } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear, formatValue } from '../../lib/format';
import { judgeChange, labelFor, polarityFor, sourceLabel } from '../../lib/signalMeta';
import { useApi } from '../../lib/useApi';
import { groupByCode } from '../trends/TrendsPage';
import { NonDiagnosticNote } from './NonDiagnosticNote';
import { PatientNotFound } from './PatientNotFound';

const PAGE_LIMIT = 100;

export type Judgment = 'better' | 'worse' | 'no change' | 'not judged';

export interface TrendRow {
  code: string;
  name: string;
  source: string;
  latest: number;
  latestAt: number;
  unitText: string;
  /** Change from the previous reading; null with a single reading. */
  delta: number | null;
  judgment: Judgment;
}

export function buildTrendRows(items: ObservationItem[]): TrendRow[] {
  return groupByCode(items).map((series) => {
    const last = series.points[series.points.length - 1];
    const previous = series.points[series.points.length - 2];
    // groupByCode never emits an empty series; the fallback keeps types honest.
    const latest = last?.value ?? 0;
    const delta = last === undefined || previous === undefined ? null : last.value - previous.value;
    const polarity = polarityFor(series.code);
    const judgeable = polarity === 'higher_is_better' || polarity === 'lower_is_better';
    const judgment: Judgment =
      delta === null || !judgeable
        ? 'not judged'
        : delta === 0
          ? 'no change'
          : judgeChange(series.code, delta) === 'better'
            ? 'better'
            : 'worse';
    return {
      code: series.code,
      name: labelFor(series.code),
      source: series.source,
      latest,
      latestAt: series.latestAt,
      unitText: series.unitText,
      delta,
      judgment,
    };
  });
}

function JudgmentCell({ judgment }: { judgment: Judgment }) {
  const className =
    judgment === 'better' ? 'arrow up' : judgment === 'worse' ? 'arrow down' : 'arrow unjudged';
  // The judgment is always a word — never color or an arrow alone.
  return <span className={className}>{judgment}</span>;
}

export function TrendTable({ patientId }: { patientId: string }) {
  const fetcher = useCallback(
    () => getClinicPatientObservations(patientId, { limit: PAGE_LIMIT }),
    [patientId],
  );
  const { data: page, error, errorStatus, loading } = useApi(fetcher);

  if (loading) {
    return <Loading label="Loading readings…" />;
  }
  if (errorStatus === 404) {
    return <PatientNotFound />;
  }
  if (error !== null || page === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  const rows = buildTrendRows(page.items);

  return (
    <div className="card">
      <h2>What the data shows</h2>
      {rows.length === 0 ? (
        <div className="empty-state">No numeric readings from this patient&apos;s sources yet.</div>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Signal</th>
                <th scope="col">Source</th>
                <th scope="col">Latest</th>
                <th scope="col">Change</th>
                <th scope="col">Judged</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code}>
                  <th scope="row">{row.name}</th>
                  <td>{sourceLabel(row.source)}</td>
                  <td>
                    {formatValue(row.latest)}
                    {row.unitText !== '' && <span className="muted"> {row.unitText}</span>}
                    <span className="muted"> · {formatDayYear(row.latestAt)}</span>
                  </td>
                  <td>
                    {row.delta === null
                      ? 'single reading'
                      : row.delta === 0
                        ? '0'
                        : `${row.delta > 0 ? '↑' : '↓'} ${formatValue(Math.abs(row.delta))}`}
                  </td>
                  <td>
                    <JudgmentCell judgment={row.judgment} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <NonDiagnosticNote />
    </div>
  );
}
