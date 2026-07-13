/**
 * Add data — BioMech report PDF upload (multipart to /biomech/reports, field
 * 'file'; imported/skipped/warnings shown, warnings as plain TEXT) and the EMR
 * connect stub (the OAuth redirect needs a registered client, so for now:
 * connect via your provider portal) with the clinic connections list.
 */

import { useState, type ChangeEvent } from 'react';
import { ApiError, messageFor } from '../../api/client';
import { getConnections, uploadBiomechReport } from '../../api/endpoints';
import type { BiomechImportOut } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';
import { ConnectionRow } from '../settings/ConnectionRow';

function UploadResult({ result }: { result: BiomechImportOut }) {
  const kind = result.report_kind === null ? 'report' : `${result.report_kind} report`;
  return (
    <div>
      <SuccessNotice>
        {result.imported} of {result.imported + result.skipped} values imported from your {kind}
        {result.assessment_at !== null && (
          <> (assessed {formatDayYear(Date.parse(result.assessment_at))})</>
        )}
        {result.skipped > 0 && <>; {result.skipped} already on file — nothing was duplicated</>}.
      </SuccessNotice>
      {result.warnings.length > 0 && (
        <div className="card">
          <div className="eyebrow">We skipped a few things</div>
          {/* Warnings come from parsing a document — always rendered as plain text. */}
          <ul className="warning-list">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function BiomechUploadCard() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<BiomechImportOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
    setResult(null);
    setError(null);
  };

  const upload = async () => {
    if (file === null) {
      return;
    }
    setUploading(true);
    setError(null);
    try {
      setResult(await uploadBiomechReport(file));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setError(`${cause.detail} — you can turn BioMech report upload back on in Sources.`);
      } else {
        setError(messageFor(cause));
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="card">
      <div className="eyebrow">BioMech report</div>
      <h2>Upload a balance or gait report</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Pick the PDF you exported from the BioMech portal. We read the numbers; you keep the
        original.
      </p>
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      {result !== null && <UploadResult result={result} />}
      <div className="file-drop">
        <label
          htmlFor="biomech-file"
          style={{ display: 'block', marginBottom: 8, fontWeight: 600 }}
        >
          📄 Report PDF
        </label>
        <input id="biomech-file" type="file" accept="application/pdf" onChange={onFileChange} />
      </div>
      <button
        className="btn secondary"
        type="button"
        disabled={file === null || uploading}
        onClick={() => {
          void upload();
        }}
      >
        {uploading ? 'Reading your report…' : 'Upload report'}
      </button>
    </div>
  );
}

function EmrConnectCard() {
  const { data: connections, error, loading, reload } = useApi(getConnections);

  return (
    <div className="card">
      <div className="eyebrow">Your medical records</div>
      <h2>Connect your records</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Soon you&apos;ll pull labs straight from your health system here — no PDFs to hunt for.
        Until then, connect via your provider portal or ask your clinic to invite you.
      </p>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }} className="muted">
        <span aria-hidden="true" style={{ fontSize: 20 }}>
          🔒
        </span>
        <p style={{ margin: 0, fontSize: 14 }}>
          When it opens, you&apos;ll sign in on <b>your health system&apos;s</b> own page. We never
          see your password — and you can disconnect anytime.
        </p>
      </div>
      <span className="pill warn" style={{ display: 'inline-block', marginTop: 12 }}>
        Coming soon
      </span>

      <h2 style={{ marginTop: 18 }}>Your clinic connections</h2>
      {loading && <Loading label="Loading connections…" />}
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      {connections !== null && connections.length === 0 && (
        <p className="muted">No clinic connections yet. Your clinic can invite you.</p>
      )}
      {connections !== null &&
        connections.map((connection) => (
          <ConnectionRow key={connection.id} connection={connection} onChanged={reload} />
        ))}
    </div>
  );
}

export function AddDataPage() {
  return (
    <div>
      <h1>Add data</h1>
      <BiomechUploadCard />
      <EmrConnectCard />
    </div>
  );
}
