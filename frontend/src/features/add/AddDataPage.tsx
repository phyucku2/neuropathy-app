/**
 * Add data — BioMech report PDF upload (multipart to /biomech/reports, field
 * 'file'; imported/skipped/warnings shown, warnings as plain TEXT) plus a pointer
 * to the REAL EMR-connect flow, which lives on the Sources surface (ADR-0028):
 * this page used to carry a duplicate, non-interactive "Coming soon" EMR card and a
 * second copy of the clinic-connections list — both already live under Sources, so
 * they were removed here (one place to manage a connection; less clutter for the
 * 60+ persona, ADR-0039). This card just links there.
 */

import { useState, type ChangeEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, messageFor } from '../../api/client';
import { uploadBiomechReport } from '../../api/endpoints';
import type { BiomechImportOut } from '../../api/types';
import { ErrorNotice, SuccessNotice } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';

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

function ConnectRecordsCard() {
  return (
    <div className="card">
      <div className="eyebrow">Your medical records</div>
      <h2>Connect your records</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Link your health system to bring in your labs — you sign in on <b>your provider&apos;s</b>
        own page, and we never see your password. You manage the connection under Sources.
      </p>
      <Link className="btn-inline" to="/settings">
        Connect under Sources
      </Link>
    </div>
  );
}

export function AddDataPage() {
  return (
    <div>
      <h1>Add data</h1>
      <BiomechUploadCard />
      <ConnectRecordsCard />
    </div>
  );
}
