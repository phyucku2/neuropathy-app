/**
 * Your Records — a READ-ONLY, display-only copy of the patient's health record
 * (product decision + ADR-0039 accessibility bar). This is the raw record as pulled
 * from the EMR, NOT the Neuropathy Status Index: no interpretation, no judged
 * direction-of-better, no diagnosis. We show what we have and are honest about what
 * we don't pull yet.
 *
 * "What we have": the patient's EMR-sourced observations (source === 'emr') from
 * GET /observations, rendered read-only — display name (labelFor), value+unit
 * (displayUnit), date, and a "from your health record" provenance line. These arrive
 * after a SMART-on-FHIR pull (ADR-0008/0028).
 *
 * "Coming soon": clearly-labeled, visually-distinct placeholders for the USCDI
 * classes the EMR exposes but we don't fetch yet — Conditions, Medications, Allergies.
 *
 * Connection state: the app has NO EMR-connections list endpoint (deliberate gap,
 * ADR-0028 §2), so the `emr_connect` capability is the best available signal for
 * whether medical-record connections are turned on. We treat it as a UI hint only
 * (the server stays the authority, ADR-0013): off → the gentle "connect in Sources"
 * prompt; on but no EMR rows → "nothing pulled yet"; on with rows → the record.
 */

import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import { getCapabilities, getObservations } from '../../api/endpoints';
import type { ObservationItem } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear, formatValue } from '../../lib/format';
import { displayUnit, labelFor } from '../../lib/signalMeta';
import { useApi } from '../../lib/useApi';

const PAGE_LIMIT = 100;

/** The standard read-only, non-diagnostic disclaimer for this surface. */
const DISCLAIMER_TEXT =
  'This is a read-only copy of your health record, not medical advice or a diagnosis. Talk to your care team about what it means.';

/** The USCDI classes the EMR exposes but we don't fetch yet (ADR-0028 gap). Each
 *  renders a plainly-labeled "Coming soon" placeholder — the words carry the state,
 *  never color alone (ADR-0039 / WCAG 1.4.1). */
const COMING_SOON: { title: string; blurb: string }[] = [
  { title: 'Conditions', blurb: 'Your medical history — the conditions on your record.' },
  { title: 'Medications', blurb: 'The medicines your record shows you are taking.' },
  { title: 'Allergies', blurb: 'Allergies and reactions noted on your record.' },
];

/** Value + unit for a reading, or its text result, or an em dash — no judgment. */
function valueText(item: ObservationItem): string {
  if (item.value !== null) {
    const unit = displayUnit(item.unit);
    return unit === '' ? formatValue(item.value) : `${formatValue(item.value)} ${unit}`;
  }
  return item.value_text ?? '—';
}

/** One record row: plain name, value+unit, date, and its provenance — read-only. */
function RecordRow({ item }: { item: ObservationItem }) {
  return (
    <div className="record">
      <div className="record-top">
        <span className="record-name">{labelFor(item.code, item.display)}</span>
        <span className="record-value">{valueText(item)}</span>
      </div>
      <div className="record-meta">
        <span>{formatDayYear(Date.parse(item.effective_at))}</span>
        {/* Provenance — this is the raw record, sourced (source==='emr') from the EMR. */}
        <span className="rec-provenance">from your health record</span>
      </div>
    </div>
  );
}

function ComingSoonSection({ title, blurb }: { title: string; blurb: string }) {
  return (
    <section className="card record-soon" aria-label={`${title} (coming soon)`}>
      <div className="record-soon-head">
        <h2>{title}</h2>
        <span className="pill off">Coming soon</span>
      </div>
      <p className="record-soon-note">{blurb}</p>
      <p className="record-soon-note">
        We&apos;ll show these here once we can read them from your record.
      </p>
    </section>
  );
}

export function RecordsPage() {
  const fetchObservations = useCallback(() => getObservations({ limit: PAGE_LIMIT }), []);
  const observations = useApi(fetchObservations);
  const capabilities = useApi(getCapabilities);

  if (observations.loading || capabilities.loading) {
    return <Loading label="Loading your records…" />;
  }
  if (
    observations.error !== null ||
    observations.data === null ||
    capabilities.error !== null ||
    capabilities.data === null
  ) {
    return (
      <ErrorNotice>
        {observations.error ?? capabilities.error ?? 'Something went wrong. Please try again.'}
      </ErrorNotice>
    );
  }

  const emrConnect = capabilities.data.capabilities.find((row) => row.key === 'emr_connect');
  // UI hint only — the server is the authority (ADR-0013); there is no connections-list
  // endpoint to confirm against (ADR-0028 §2), so the capability toggle stands in.
  const connectionsOn = emrConnect === undefined || emrConnect.active;

  // EMR-sourced rows only — this surface is the raw record, newest first. Other sources
  // (BioMech, check-ins, phone/watch) live in Trends, not here.
  const records = observations.data.items
    .filter((item) => item.source === 'emr')
    .sort((a, b) => Date.parse(b.effective_at) - Date.parse(a.effective_at));

  return (
    <div>
      <h1>Your records</h1>
      <p className="muted records-intro">
        A read-only copy of the health information we&apos;ve pulled from your medical record. This
        is your record as-is — we don&apos;t change it or judge it.
      </p>

      <h2>Labs and results</h2>
      {!connectionsOn ? (
        <div className="card">
          <p style={{ marginTop: 0 }}>
            <b>No health record connected yet.</b>
          </p>
          <p className="muted" style={{ marginBottom: 12 }}>
            Connect your medical record in Sources, and your labs and results will show here.
          </p>
          <Link className="btn-inline" to="/settings">
            Go to Sources
          </Link>
        </div>
      ) : records.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <p style={{ marginTop: 0 }}>
              <b>No results pulled from your record yet.</b>
            </p>
            <p style={{ marginBottom: 0 }}>
              Once you pull your labs from the connection in Sources, they&apos;ll appear here.
            </p>
          </div>
        </div>
      ) : (
        <div className="card">
          {records.map((item, index) => (
            <RecordRow key={`${item.code}:${item.effective_at}:${String(index)}`} item={item} />
          ))}
        </div>
      )}

      {/* What we don't pull yet — honest, visually-distinct placeholders (ADR-0028 gap). */}
      {COMING_SOON.map((section) => (
        <ComingSoonSection key={section.title} title={section.title} blurb={section.blurb} />
      ))}

      <p className="disclaimer" role="note">
        {DISCLAIMER_TEXT}
      </p>
    </div>
  );
}
