/**
 * Medications & supplements — the patient-entered change log (ADR-0045 P2). A LIST the patient
 * keeps: register a medication/supplement, append a dose change, or mark one stopped. Every
 * change is its OWN dated entry (append-only) and the full set is the history — nothing is ever
 * overwritten. The folded current list + per-med change log come from GET /medications.
 *
 * NON-DIAGNOSTIC (CLAUDE.md, co-located note below): the app only records this list — it never
 * adjusts, checks, interacts with, or recommends medicines. All entries are patient-entered.
 *
 * Capability-gated (`ingest_medications`): both the list read and every write 409 when the
 * source is turned off, handled here with a pointer to Sources (mirrors AddDataPage/CheckIn).
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, messageFor } from '../../api/client';
import { getMedications, postMedication, postMedicationChange } from '../../api/endpoints';
import type { MedicationKind, MedicationOut } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { formatDayYear, formatValue } from '../../lib/format';
import { useApi } from '../../lib/useApi';

/** The patient's LOCAL calendar day as YYYY-MM-DD (never toISOString — that is UTC and an
 *  evening entry west of UTC would land on tomorrow). Used as the date-input default/max. */
function todayLocalIso(now = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${String(now.getFullYear())}-${month}-${day}`;
}

const KIND_OPTIONS: { value: MedicationKind; label: string }[] = [
  { value: 'prescription', label: 'Prescription' },
  { value: 'otc', label: 'Over-the-counter' },
  { value: 'supplement', label: 'Supplement' },
];

const KIND_LABEL: Record<MedicationKind, string> = {
  prescription: 'Prescription',
  otc: 'Over-the-counter',
  supplement: 'Supplement',
};

const CHANGE_LABEL: Record<string, string> = {
  added: 'Added',
  dose_changed: 'Dose changed',
  stopped: 'Stopped',
};

/** "50 mg", "1 tablet twice daily", or null when there is no dose to describe. */
function doseLine(amount: number | null, unit: string | null, text: string | null): string | null {
  if (text !== null && text.trim() !== '') {
    return text;
  }
  if (amount !== null) {
    return unit !== null && unit.trim() !== ''
      ? `${formatValue(amount)} ${unit}`
      : formatValue(amount);
  }
  return null;
}

/** Turn a possibly-empty numeric field into a number|null (a blank means "not given"). */
function toAmount(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : Number(trimmed);
}

/** Turn a possibly-empty text field into string|null. */
function toText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

function CapabilityOffCard() {
  return (
    <div className="card">
      <div className="eyebrow">Turned off</div>
      <h2>Medications is turned off</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        This source is turned off right now, so nothing is being recorded.{' '}
        <Link className="link" to="/settings">
          You can turn it back on in Sources.
        </Link>
      </p>
    </div>
  );
}

function AddMedicationForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState('');
  const [kind, setKind] = useState<MedicationKind>('prescription');
  const [doseAmount, setDoseAmount] = useState('');
  const [doseUnit, setDoseUnit] = useState('');
  const [doseText, setDoseText] = useState('');
  const [prescriber, setPrescriber] = useState('');
  const [reason, setReason] = useState('');
  const [startedOn, setStartedOn] = useState(todayLocalIso());
  const [error, setError] = useState<string | null>(null);
  const [featureOff, setFeatureOff] = useState(false);
  const [savedName, setSavedName] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (name.trim() === '') {
      return;
    }
    setSaving(true);
    setError(null);
    setFeatureOff(false);
    setSavedName(null);
    try {
      await postMedication({
        name: name.trim(),
        kind,
        dose_amount: toAmount(doseAmount),
        dose_unit: toText(doseUnit),
        dose_text: toText(doseText),
        prescriber: toText(prescriber),
        reason: toText(reason),
        started_on: startedOn,
      });
      setSavedName(name.trim());
      setName('');
      setDoseAmount('');
      setDoseUnit('');
      setDoseText('');
      setPrescriber('');
      setReason('');
      setStartedOn(todayLocalIso());
      onAdded();
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
      <div className="eyebrow">Add to your list</div>
      <h2>Add a medication or supplement</h2>
      {savedName !== null && <SuccessNotice>Added {savedName} to your list.</SuccessNotice>}
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
        <label htmlFor="med-name">Name</label>
        <input
          id="med-name"
          type="text"
          maxLength={200}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="med-kind">Kind</label>
        <select
          id="med-kind"
          value={kind}
          onChange={(event) => {
            setKind(event.target.value as MedicationKind);
          }}
        >
          {KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="med-dose-amount">Dose amount (optional)</label>
        <input
          id="med-dose-amount"
          type="number"
          inputMode="decimal"
          value={doseAmount}
          onChange={(event) => {
            setDoseAmount(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="med-dose-unit">Dose unit (optional)</label>
        <input
          id="med-dose-unit"
          type="text"
          maxLength={40}
          placeholder="e.g. mg"
          value={doseUnit}
          onChange={(event) => {
            setDoseUnit(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="med-dose-text">Or describe the dose (optional)</label>
        <input
          id="med-dose-text"
          type="text"
          maxLength={200}
          placeholder="e.g. 1 tablet twice daily"
          value={doseText}
          onChange={(event) => {
            setDoseText(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="med-prescriber">Prescriber (optional)</label>
        <input
          id="med-prescriber"
          type="text"
          maxLength={200}
          value={prescriber}
          onChange={(event) => {
            setPrescriber(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="med-reason">Reason (optional)</label>
        <input
          id="med-reason"
          type="text"
          maxLength={500}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="med-started">Started on</label>
        <input
          id="med-started"
          type="date"
          max={todayLocalIso()}
          value={startedOn}
          onChange={(event) => {
            setStartedOn(event.target.value);
          }}
        />
      </div>
      <button
        className="btn"
        type="button"
        disabled={name.trim() === '' || saving}
        onClick={() => {
          void submit();
        }}
      >
        {saving ? 'Saving…' : 'Add to my list'}
      </button>
    </div>
  );
}

function ChangeForm({ med, onChanged }: { med: MedicationOut; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [changeType, setChangeType] = useState<'dose_changed' | 'stopped'>('dose_changed');
  const [doseAmount, setDoseAmount] = useState('');
  const [doseUnit, setDoseUnit] = useState('');
  const [doseText, setDoseText] = useState('');
  const [reason, setReason] = useState('');
  const [effectiveDate, setEffectiveDate] = useState(todayLocalIso());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // A dose_changed entry with no dose at all records nothing (the backend 422s it), so the
  // submit stays disabled until at least one dose field is present; `stopped` needs none.
  const doseGiven = doseAmount.trim() !== '' || doseUnit.trim() !== '' || doseText.trim() !== '';
  const canSubmit = changeType === 'stopped' || doseGiven;

  const submit = async () => {
    if (!canSubmit) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await postMedicationChange(med.medication_id, {
        change_type: changeType,
        dose_amount: changeType === 'stopped' ? null : toAmount(doseAmount),
        dose_unit: changeType === 'stopped' ? null : toText(doseUnit),
        dose_text: changeType === 'stopped' ? null : toText(doseText),
        reason: toText(reason),
        effective_date: effectiveDate,
      });
      setOpen(false);
      setDoseAmount('');
      setDoseUnit('');
      setDoseText('');
      setReason('');
      setEffectiveDate(todayLocalIso());
      onChanged();
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button
        className="btn-inline"
        type="button"
        aria-label={`Record a change for ${med.name}`}
        onClick={() => {
          setOpen(true);
        }}
      >
        Record a change
      </button>
    );
  }

  const idBase = `change-${med.medication_id}`;
  return (
    <div className="med-change">
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      <fieldset className="seg-group">
        <legend>What kind of change?</legend>
        <div className="seg-row" role="radiogroup" aria-label={`Change type for ${med.name}`}>
          <button
            type="button"
            className="seg"
            role="radio"
            aria-checked={changeType === 'dose_changed'}
            onClick={() => {
              setChangeType('dose_changed');
            }}
          >
            Dose change
          </button>
          <button
            type="button"
            className="seg"
            role="radio"
            aria-checked={changeType === 'stopped'}
            onClick={() => {
              setChangeType('stopped');
            }}
          >
            Mark stopped
          </button>
        </div>
      </fieldset>
      {changeType === 'dose_changed' && (
        <>
          <div className="field">
            <label htmlFor={`${idBase}-amount`}>New dose amount</label>
            <input
              id={`${idBase}-amount`}
              type="number"
              inputMode="decimal"
              value={doseAmount}
              onChange={(event) => {
                setDoseAmount(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor={`${idBase}-unit`}>New dose unit</label>
            <input
              id={`${idBase}-unit`}
              type="text"
              maxLength={40}
              placeholder="e.g. mg"
              value={doseUnit}
              onChange={(event) => {
                setDoseUnit(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor={`${idBase}-text`}>Or describe the new dose</label>
            <input
              id={`${idBase}-text`}
              type="text"
              maxLength={200}
              value={doseText}
              onChange={(event) => {
                setDoseText(event.target.value);
              }}
            />
          </div>
        </>
      )}
      <div className="field">
        <label htmlFor={`${idBase}-reason`}>Reason (optional)</label>
        <input
          id={`${idBase}-reason`}
          type="text"
          maxLength={500}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor={`${idBase}-date`}>Date the change took effect</label>
        <input
          id={`${idBase}-date`}
          type="date"
          max={todayLocalIso()}
          value={effectiveDate}
          onChange={(event) => {
            setEffectiveDate(event.target.value);
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
        {saving ? 'Saving…' : 'Save this change'}
      </button>
      <button
        className="btn ghost"
        type="button"
        onClick={() => {
          setOpen(false);
          setError(null);
        }}
      >
        Cancel
      </button>
    </div>
  );
}

function MedicationCard({ med, onChanged }: { med: MedicationOut; onChanged: () => void }) {
  const current = doseLine(med.current_dose_amount, med.current_dose_unit, med.current_dose_text);
  return (
    <div className="card">
      <div className="handout-row-head">
        <span className="handout-metric">{med.name}</span>
        <span className="chip">{KIND_LABEL[med.kind]}</span>
        <span className={med.status === 'active' ? 'pill on' : 'pill off'}>
          {med.status === 'active' ? 'Active' : 'Stopped'}
        </span>
        <span className="chip">You entered</span>
      </div>
      <p className="handout-span">
        {current === null ? 'No dose recorded.' : `Current dose: ${current}.`}
        {med.prescriber !== null &&
          med.prescriber.trim() !== '' &&
          ` Prescriber: ${med.prescriber}.`}{' '}
        Started {formatDayYear(Date.parse(med.started_on))}.
      </p>
      <details>
        <summary>Change history ({med.changes.length})</summary>
        <ul className="log-list">
          {med.changes.map((change, index) => {
            const dose = doseLine(change.dose_amount, change.dose_unit, change.dose_text);
            return (
              <li key={`${change.change_type}-${change.effective_at}-${String(index)}`}>
                <b>{CHANGE_LABEL[change.change_type] ?? change.change_type}</b>{' '}
                {formatDayYear(Date.parse(change.effective_at))}
                {dose !== null && ` — ${dose}`}
                {change.reason !== null && change.reason.trim() !== '' && ` (${change.reason})`}
              </li>
            );
          })}
        </ul>
      </details>
      {med.status === 'active' && <ChangeForm med={med} onChanged={onChanged} />}
    </div>
  );
}

export function MedsPage() {
  const { data, error, errorStatus, loading, reload } = useApi(getMedications);

  return (
    <div>
      <h1>Medications &amp; supplements</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        A list you keep of your medications and supplements to bring to your visits.
      </p>
      {/* The non-diagnostic guardrail, co-located with the capture (CLAUDE.md). */}
      <p className="disclaimer" role="note">
        This is a list you keep — the app never adjusts, checks, or recommends medicines. Talk to
        your care team about anything you take.
      </p>

      {errorStatus === 409 ? (
        <CapabilityOffCard />
      ) : (
        <>
          {/* The add form stays mounted across reloads (a reload flips `loading` true after a
              successful write) so its "saved" confirmation is never unmounted mid-flash. */}
          <AddMedicationForm onAdded={reload} />
          {loading && data === null && <Loading label="Loading your list…" />}
          {error !== null && <ErrorNotice>{error}</ErrorNotice>}
          {data !== null && data.items.length === 0 && (
            <p className="muted">Nothing on your list yet. Add your first medication above.</p>
          )}
          {data?.items.map((med) => (
            <MedicationCard key={med.medication_id} med={med} onChanged={reload} />
          ))}
        </>
      )}
    </div>
  );
}
