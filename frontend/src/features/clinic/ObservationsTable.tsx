/**
 * Observations tab — the consented patient's raw analyzable records, newest
 * first, paged exactly like the backend contract (GET
 * /clinic/patients/{id}/observations with limit/offset).
 */

import { useCallback, useState } from 'react';
import { getClinicPatientObservations } from '../../api/endpoints';
import type { ObservationItem } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear, formatValue } from '../../lib/format';
import { displayUnit, labelFor, sourceLabel } from '../../lib/signalMeta';
import { useApi } from '../../lib/useApi';
import { PatientNotFound } from './PatientNotFound';

const PAGE_SIZE = 20;

function valueText(item: ObservationItem): string {
  if (item.value !== null) {
    const unit = displayUnit(item.unit);
    return unit === '' ? formatValue(item.value) : `${formatValue(item.value)} ${unit}`;
  }
  return item.value_text ?? '—';
}

export function ObservationsTable({ patientId }: { patientId: string }) {
  const [offset, setOffset] = useState(0);
  const fetcher = useCallback(
    () => getClinicPatientObservations(patientId, { limit: PAGE_SIZE, offset }),
    [patientId, offset],
  );
  const { data: page, error, errorStatus, loading } = useApi(fetcher);

  if (loading) {
    return <Loading label="Loading observations…" />;
  }
  if (errorStatus === 404) {
    return <PatientNotFound />;
  }
  if (error !== null || page === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  if (page.total === 0) {
    return (
      <div className="card">
        <h2>Observations</h2>
        <div className="empty-state">No observations recorded yet.</div>
      </div>
    );
  }

  const from = page.offset + 1;
  const to = page.offset + page.items.length;

  return (
    <div className="card">
      <h2>Observations</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Measure</th>
              <th scope="col">Value</th>
              <th scope="col">Source</th>
              <th scope="col">Date</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((item, index) => (
              <tr key={`${item.code}:${item.effective_at}:${String(index)}`}>
                <th scope="row">{labelFor(item.code, item.display)}</th>
                <td>{valueText(item)}</td>
                <td>{sourceLabel(item.source)}</td>
                <td>{formatDayYear(Date.parse(item.effective_at))}</td>
                <td>{item.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button
          type="button"
          className="btn-inline"
          disabled={page.offset === 0}
          onClick={() => {
            setOffset(Math.max(0, offset - PAGE_SIZE));
          }}
        >
          Newer
        </button>
        <span className="muted">
          Showing {String(from)}–{String(to)} of {String(page.total)}
        </span>
        <button
          type="button"
          className="btn-inline"
          disabled={to >= page.total}
          onClick={() => {
            setOffset(offset + PAGE_SIZE);
          }}
        >
          Older
        </button>
      </div>
    </div>
  );
}
