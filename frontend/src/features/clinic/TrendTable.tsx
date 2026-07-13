/**
 * Cross-source trend table (mockup "What the data shows"): one row per metric
 * across lab / check-in / BioMech sources with the latest value, the change
 * since the previous reading, and a judged direction from the shared signal
 * semantics (lib/signalMeta — the UI mirror of the backend registry).
 *
 * Judgment honesty: a metric whose polarity is unknown or in-range, or with a
 * single reading, says "not judged" — NEVER "stable". The word "stable" is a
 * clinical claim the data does not support here. A metric whose latest two
 * readings carry different unit strings is likewise "not judged": the numbers
 * are incomparable, so the table says "unit changed" instead of a delta.
 *
 * Completeness: observations are paged in full (up to a hard safety cap), not
 * just the newest page — otherwise an old lab silently vanishes or fakes a
 * "single reading". When the cap truncates, the table says so explicitly.
 */

import { useCallback, useEffect } from 'react';
import { getClinicPatientObservations } from '../../api/endpoints';
import type { ObservationItem } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear, formatValue } from '../../lib/format';
import { judgeChange, polarityFor, sourceLabel } from '../../lib/signalMeta';
import { useApi } from '../../lib/useApi';
import { changeSincePrevious, groupByCode } from '../trends/TrendsPage';
import { NonDiagnosticNote } from './NonDiagnosticNote';
import { PatientNotFound } from './PatientNotFound';

const PAGE_LIMIT = 100;
/** Hard safety cap: at most 10 pages (1,000 rows) feed the table. */
const MAX_PAGES = 10;

interface AllObservations {
  items: ObservationItem[];
  total: number;
}

/**
 * Page through EVERY observation (newest first), up to the safety cap — one
 * page would hide any metric whose readings fall outside the newest 100.
 */
async function fetchAllObservations(patientId: string): Promise<AllObservations> {
  const items: ObservationItem[] = [];
  let total = 0;
  for (let pageIndex = 0; pageIndex < MAX_PAGES; pageIndex += 1) {
    const page = await getClinicPatientObservations(patientId, {
      limit: PAGE_LIMIT,
      offset: pageIndex * PAGE_LIMIT,
    });
    items.push(...page.items);
    total = page.total;
    if (items.length >= total || page.items.length === 0) {
      break;
    }
  }
  return { items, total };
}

export type Judgment = 'better' | 'worse' | 'no change' | 'not judged';

export interface TrendRow {
  code: string;
  name: string;
  source: string;
  latest: number;
  latestAt: number;
  unitText: string;
  /** Change from the previous reading; null with a single reading or a unit change. */
  delta: number | null;
  /** The latest two readings carry different unit strings — incomparable. */
  unitChanged: boolean;
  judgment: Judgment;
}

export function buildTrendRows(items: ObservationItem[]): TrendRow[] {
  return groupByCode(items).map((series) => {
    const last = series.points[series.points.length - 1];
    // groupByCode never emits an empty series; the fallback keeps types honest.
    const latest = last?.value ?? 0;
    const { delta, unitChanged } = changeSincePrevious(series.points);
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
      // The series name already prefers the backend's display over a raw code
      // (labelFor with the latest reading's display) — same as Observations.
      name: series.name,
      source: series.source,
      latest,
      latestAt: series.latestAt,
      unitText: series.unitText,
      delta,
      unitChanged,
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

export function TrendTable({
  patientId,
  onNotFound,
}: {
  patientId: string;
  onNotFound?: () => void;
}) {
  const fetcher = useCallback(() => fetchAllObservations(patientId), [patientId]);
  const { data, error, errorStatus, loading } = useApi(fetcher);

  useEffect(() => {
    if (errorStatus === 404) {
      onNotFound?.();
    }
  }, [errorStatus, onNotFound]);

  if (loading) {
    return <Loading label="Loading readings…" />;
  }
  if (errorStatus === 404) {
    return <PatientNotFound />;
  }
  if (error !== null || data === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  const rows = buildTrendRows(data.items);

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
                    {row.unitChanged
                      ? 'unit changed'
                      : row.delta === null
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
      {data.total > data.items.length && (
        <p className="muted">
          Based on the most recent {data.items.length.toLocaleString('en-US')} of{' '}
          {data.total.toLocaleString('en-US')} records.
        </p>
      )}
      <NonDiagnosticNote />
    </div>
  );
}
