/**
 * Between-visit notes & events (ADR-0045 P2). The patient records something that happened
 * between visits — a fall, an ER visit, a new provider, a hospitalization, a new supplement —
 * or a plain note in their own words. Each is one append-only, dated entry; the list is
 * newest-first. The note is the patient's own words, shown verbatim.
 *
 * SAFETY (owner decision, ADR-0045): a PERSISTENT, non-dismissible emergency banner rides the
 * compose surface. The note channel is NOT monitored in real time and there is NO red-flag
 * scanning or triage — the banner says so and points to 911 / the clinic for anything urgent.
 *
 * Capability-gated (`ingest_events`): the list read and every write 409 when the source is
 * turned off, handled here with a pointer to Sources.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, messageFor } from '../../api/client';
import { getEvents, postEvent } from '../../api/endpoints';
import type { EventType } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';

/** The patient's LOCAL calendar day as YYYY-MM-DD (never toISOString — that is UTC). */
function todayLocalIso(now = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${String(now.getFullYear())}-${month}-${day}`;
}

const TYPE_OPTIONS: { value: EventType; label: string }[] = [
  { value: 'fall', label: 'Fall' },
  { value: 'er_visit', label: 'ER visit' },
  { value: 'new_provider', label: 'New provider' },
  { value: 'hospitalization', label: 'Hospitalization' },
  { value: 'new_supplement', label: 'New supplement' },
  { value: 'note', label: 'Note' },
];

const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  TYPE_OPTIONS.map((option) => [option.value, option.label]),
);

/** The persistent, non-dismissible emergency banner (ADR-0045 owner decision). Always rendered
 *  on the compose surface — there is no close control by design. */
function EmergencyBanner() {
  return (
    <div className="emergency-banner" role="note" aria-label="Emergency information">
      <b>
        Notes are reviewed by your clinician when they can — this is not monitored in real time.
      </b>{' '}
      If this is an emergency, call 911. If it&apos;s urgent, call your clinic.
    </div>
  );
}

function CapabilityOffCard() {
  return (
    <div className="card">
      <div className="eyebrow">Turned off</div>
      <h2>Notes &amp; events is turned off</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        This source is turned off right now, so nothing is being recorded.{' '}
        <Link className="link" to="/settings">
          You can turn it back on in Sources.
        </Link>
      </p>
    </div>
  );
}

function RecordEventForm({ onRecorded }: { onRecorded: () => void }) {
  const [type, setType] = useState<EventType>('fall');
  const [effectiveDate, setEffectiveDate] = useState(todayLocalIso());
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [featureOff, setFeatureOff] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  // A `note` event with no note records nothing (the backend 422s it), so the submit stays
  // disabled until a note is present; every other type allows an optional note.
  const noteRequired = type === 'note';
  const canSubmit = !noteRequired || note.trim() !== '';

  const submit = async () => {
    if (!canSubmit) {
      return;
    }
    setSaving(true);
    setError(null);
    setFeatureOff(false);
    setSaved(false);
    try {
      await postEvent({
        type,
        effective_date: effectiveDate,
        note: note.trim() === '' ? null : note.trim(),
      });
      setSaved(true);
      setNote('');
      setEffectiveDate(todayLocalIso());
      onRecorded();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setFeatureOff(true);
      }
      setError(messageFor(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <div className="eyebrow">Record something</div>
      <h2>Add a note or event</h2>
      {saved && <SuccessNotice>Saved to your between-visit list.</SuccessNotice>}
      {error !== null && (
        <ErrorNotice>
          {error}
          {featureOff && (
            <>
              {' '}
              <Link className="link" to="/settings">
                You can turn it back on in Sources.
              </Link>
            </>
          )}
        </ErrorNotice>
      )}
      <div className="field">
        <label htmlFor="event-type">What happened?</label>
        <select
          id="event-type"
          value={type}
          onChange={(event) => {
            setType(event.target.value as EventType);
          }}
        >
          {TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="event-date">Date</label>
        <input
          id="event-date"
          type="date"
          max={todayLocalIso()}
          value={effectiveDate}
          onChange={(event) => {
            setEffectiveDate(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="event-note">
          {noteRequired ? 'Note (in your own words)' : 'Note (optional, in your own words)'}
        </label>
        <textarea
          id="event-note"
          rows={4}
          maxLength={500}
          value={note}
          onChange={(event) => {
            setNote(event.target.value);
          }}
        />
      </div>
      <button
        className="btn"
        type="button"
        disabled={!canSubmit || saving}
        onClick={() => {
          void submit();
        }}
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  );
}

export function EventsPage() {
  const { data, error, errorStatus, loading, reload } = useApi(getEvents);

  return (
    <div>
      <h1>Notes &amp; events</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        A place to record things that happen between visits, in your own words, to share with your
        care team.
      </p>
      <EmergencyBanner />

      {errorStatus === 409 ? (
        <CapabilityOffCard />
      ) : (
        <>
          {/* The record form stays mounted across reloads (a reload flips `loading` true after a
              successful write) so its "saved" confirmation is never unmounted mid-flash. */}
          <RecordEventForm onRecorded={reload} />
          {loading && data === null && <Loading label="Loading your notes…" />}
          {error !== null && <ErrorNotice>{error}</ErrorNotice>}
          <h2>Your between-visit list</h2>
          {data !== null && data.items.length === 0 && (
            <p className="muted">Nothing recorded yet. Add your first note or event above.</p>
          )}
          {data?.items.map((item) => (
            <div className="card" key={item.event_id}>
              <div className="handout-row-head">
                <span className="handout-metric">{TYPE_LABEL[item.type] ?? item.type}</span>
                <span className="chip">{formatDayYear(Date.parse(item.effective_at))}</span>
                <span className="chip">You entered</span>
              </div>
              {item.note !== null && item.note.trim() !== '' && (
                <>
                  <p className="handout-span muted" style={{ marginBottom: 0 }}>
                    In your own words:
                  </p>
                  {/* The note is the patient's own words — rendered verbatim as plain text. */}
                  <p className="handout-span">{item.note}</p>
                </>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
