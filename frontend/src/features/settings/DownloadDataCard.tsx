/**
 * "Download my data" (ADR-0031) — the right-of-access card, deliberately placed ABOVE
 * the danger zone and clearly separated from it: exporting your record is the safe,
 * reassuring counterpart to deleting it.
 *
 * One button fetches the current record (GET /me/export) and hands it to the
 * platform-appropriate delivery seam (src/native/exportData.ts): a file download +
 * CSV on web, a written file + OS Share sheet on native. While the request is in
 * flight a role=status tells the patient their data is being prepared and every
 * control is disabled; any API failure is surfaced verbatim in a role=alert.
 *
 * The payload never contains a token, secret, or password hash (backend
 * schemas/export.py) — this card only requests and delivers it.
 */

import { useState } from 'react';
import { ApiError, messageFor } from '../../api/client';
import { exportMyData } from '../../api/endpoints';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { saveExport } from '../../native/exportData';

export function DownloadDataCard() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const onDownload = async () => {
    setPending(true);
    setError(null);
    setDone(false);
    try {
      const data = await exportMyData();
      await saveExport(data);
      setDone(true);
    } catch (cause) {
      // A 403/500 etc. carries the backend's own detail — surfaced verbatim.
      setError(cause instanceof ApiError ? cause.detail : messageFor(cause));
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <h2>Your data</h2>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          Download a copy of your current account and health data — the record itself, your
          observations (also as a spreadsheet), and your connections. It never includes passwords or
          access tokens.
        </p>
        {error !== null && <ErrorNotice>{error}</ErrorNotice>}
        {pending && <Loading label="Preparing your data…" />}
        {done && !pending && error === null && <SuccessNotice>Your data is ready.</SuccessNotice>}
        <button
          type="button"
          className="btn-inline"
          disabled={pending}
          onClick={() => {
            void onDownload();
          }}
        >
          Download my data
        </button>
      </div>
    </>
  );
}
