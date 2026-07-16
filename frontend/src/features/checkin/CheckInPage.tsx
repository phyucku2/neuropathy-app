/**
 * Daily check-in — the three 0-4 ADL questions as the mockup's segmented
 * buttons. POST /adl; a same-day re-submission shows the superseded notice;
 * a 409 means the feature is turned off (server-enforced toggle, ADR-0013).
 *
 * Offline (ADR-0030): a NETWORK failure (fetch TypeError — never an API 4xx/5xx,
 * which keep their verbatim handling) queues the answers on-device and shows a
 * saved-on-this-device state; the queue syncs via offlineSync when connectivity
 * returns, and this page flips to the normal saved view when its entry lands.
 */

import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, messageFor } from '../../api/client';
import { getCapabilities, postAdlCheckIn } from '../../api/endpoints';
import type { AdlCheckInOut } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { useApi } from '../../lib/useApi';
import {
  enqueueCheckIn,
  getQueuedCheckIn,
  removeQueuedCheckIn,
  type QueuedCheckIn,
} from './offlineQueue';
import {
  consumeDroppedNotices,
  flushQueuedCheckIns,
  subscribeFlushOutcomes,
  type DroppedCheckIn,
  type SyncedCheckIn,
} from './offlineSync';

/** Capability key gating the symptom items (pain + numbness) — ADR-0034 Phase 1. */
const SYMPTOMS_CAPABILITY = 'ingest_symptoms';

/** 0-4 for the function questions; 0-10 for the symptom NRS-aligned items. */
const FUNCTION_VALUES = [0, 1, 2, 3, 4] as const;
const SYMPTOM_VALUES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as const;

/**
 * The browser-LOCAL calendar day as YYYY-MM-DD. Never toISOString(): that is
 * UTC, and an evening check-in west of UTC would land on tomorrow's date,
 * breaking same-day supersede.
 */
export function localCheckInDate(now = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${String(now.getFullYear())}-${month}-${day}`;
}

/** "Jul 14" from a stored YYYY-MM-DD — local date parts, never a UTC re-parse. */
function displayDay(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Date(year ?? 0, (month ?? 1) - 1, day ?? 1).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

type FunctionKey = 'walking' | 'stairs' | 'balance_confidence';
type SymptomKey = 'pain' | 'numbness';

interface Question<K extends string = string> {
  key: K;
  prompt: string;
  low: string;
  high: string;
  /** The answer scale for this question (0-4 function, 0-10 symptom). */
  values: readonly number[];
}

const QUESTIONS: Question<FunctionKey>[] = [
  {
    key: 'walking',
    prompt: 'How did walking feel today?',
    low: 'Very hard',
    high: 'Easy',
    values: FUNCTION_VALUES,
  },
  {
    key: 'stairs',
    prompt: 'How were stairs today?',
    low: 'Very hard',
    high: 'Easy',
    values: FUNCTION_VALUES,
  },
  {
    key: 'balance_confidence',
    prompt: 'How confident did you feel about your balance?',
    low: 'Not confident',
    high: 'Very confident',
    values: FUNCTION_VALUES,
  },
];

// Symptom items (ADR-0034 Phase 1), shown only when the ingest_symptoms toggle is on.
// Higher = WORSE here (inverse of the function questions), so 0 anchors "none" and 10
// the most severe. These are validated-measure-ALIGNED (pain = 0-10 NRS; numbness =
// NTSS-6-aligned), NOT the copyrighted instruments themselves — nothing here claims to
// be a validated/clinical measure (licensing + exact items pending confirmation).
const SYMPTOM_QUESTIONS: Question<SymptomKey>[] = [
  {
    key: 'pain',
    prompt: 'What was your worst pain today?',
    low: 'No pain',
    high: 'Worst imaginable',
    values: SYMPTOM_VALUES,
  },
  {
    key: 'numbness',
    prompt: 'How strong was any numbness or tingling today?',
    low: 'None',
    high: 'Most severe',
    values: SYMPTOM_VALUES,
  },
];

function SegmentedAnswer({
  question,
  value,
  onChange,
}: {
  question: Question;
  value: number | null;
  onChange: (answer: number) => void;
}) {
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const values = question.values;
  const maxValue = values[values.length - 1] ?? 0;

  // WAI-ARIA radio-group keyboard pattern: arrow keys move focus AND select,
  // wrapping at the ends.
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, answer: number) => {
    const step =
      event.key === 'ArrowRight' || event.key === 'ArrowDown'
        ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp'
          ? -1
          : 0;
    if (step === 0) {
      return;
    }
    event.preventDefault();
    // Values are contiguous 0..max, so the value doubles as its index.
    const next = (answer + step + values.length) % values.length;
    onChange(next);
    optionRefs.current[next]?.focus();
  };

  // Scale anchors in the accessible name so AT users hear what the endpoints mean.
  const nameFor = (answer: number): string | undefined => {
    if (answer === 0) return `0 — ${question.low}`;
    if (answer === maxValue) return `${String(answer)} — ${question.high}`;
    return undefined;
  };

  return (
    <fieldset className="seg-group">
      <legend>{question.prompt}</legend>
      <div className="seg-row" role="radiogroup" aria-label={question.prompt}>
        {values.map((answer) => (
          <button
            key={answer}
            ref={(element) => {
              optionRefs.current[answer] = element;
            }}
            type="button"
            className="seg"
            role="radio"
            aria-checked={value === answer}
            aria-label={nameFor(answer)}
            // Roving tabindex: the selected option — or the first, before any
            // selection — is the group's single tab stop.
            tabIndex={value === answer || (value === null && answer === values[0]) ? 0 : -1}
            onKeyDown={(event) => {
              onKeyDown(event, answer);
            }}
            onClick={() => {
              onChange(answer);
            }}
          >
            {answer}
          </button>
        ))}
      </div>
      <div className="seg-anchors">
        <span>
          {values[0]} · {question.low}
        </span>
        <span>
          {maxValue} · {question.high}
        </span>
      </div>
    </fieldset>
  );
}

export function CheckInPage() {
  // The queue is bound to the signed-in account (ADR-0030 per-user binding). This
  // page renders inside PatientArea, which guarantees a loaded user; the null
  // fallback only satisfies the type and skips queue access when it cannot apply.
  const { user } = useAuth();
  const ownerId = user?.user_id ?? null;
  const [answers, setAnswers] = useState<Record<FunctionKey, number | null>>({
    walking: null,
    stairs: null,
    balance_confidence: null,
  });
  // Symptom answers (ADR-0034 Phase 1) — only collected/sent when the toggle is on.
  const [symptoms, setSymptoms] = useState<Record<SymptomKey, number | null>>({
    pain: null,
    numbness: null,
  });
  // The symptom capture toggle (ingest_symptoms, ADR-0013). We gate the whole page on
  // this read RESOLVING (below): a patient whose toggle is on but whose capabilities
  // read is merely slow must not be shown a function-only form they could submit before
  // the symptom section ever appears. A genuinely FAILED read still reads as OFF (safe
  // default; keeps the page usable offline) — only an in-flight read blocks.
  const { data: capabilityData, loading: capabilityLoading } = useApi(getCapabilities);
  const symptomsOn =
    capabilityData?.capabilities.some((c) => c.key === SYMPTOMS_CAPABILITY && c.active) ?? false;
  const [result, setResult] = useState<AdlCheckInOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [featureOff, setFeatureOff] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // Offline queue state (ADR-0030): this submission captured offline; today's
  // already-queued entry (shown as a replaceable notice); one-time sync notices
  // for entries the server refused (409/422) during a background flush.
  const [offlineSaved, setOfflineSaved] = useState<QueuedCheckIn | null>(null);
  const [queuedToday, setQueuedToday] = useState<QueuedCheckIn | null>(() =>
    ownerId === null ? null : getQueuedCheckIn(ownerId, localCheckInDate()),
  );
  const [syncNotices, setSyncNotices] = useState<{ id: number; text: string }[]>([]);
  const noticeId = useRef(0);
  const [lastSynced, setLastSynced] = useState<SyncedCheckIn[]>([]);
  const [lastDropped, setLastDropped] = useState<DroppedCheckIn[]>([]);

  useEffect(() => {
    const pullNotices = () => {
      const dropped = consumeDroppedNotices();
      if (dropped.length > 0) {
        setSyncNotices((current) => {
          const next = [...current];
          for (const { entry, detail } of dropped) {
            const text = `An offline check-in from ${displayDay(entry.check_in_date)} couldn't be sent: ${detail}`;
            // Identical consecutive notices collapse into one — repeating the
            // same refusal adds noise, not information.
            if (next[next.length - 1]?.text === text) {
              continue;
            }
            noticeId.current += 1;
            next.push({ id: noticeId.current, text });
          }
          return next;
        });
      }
    };
    pullNotices();
    return subscribeFlushOutcomes((outcome) => {
      pullNotices();
      setLastSynced(outcome.synced);
      setLastDropped(outcome.dropped);
      setQueuedToday(ownerId === null ? null : getQueuedCheckIn(ownerId, localCheckInDate()));
    });
  }, [ownerId]);

  // A background flush delivered THIS page's offline capture: show the normal
  // saved view with the server's real response (score + superseded flag).
  useEffect(() => {
    if (offlineSaved === null) {
      return;
    }
    const match = lastSynced.find((s) => s.entry.check_in_date === offlineSaved.check_in_date);
    if (match !== undefined) {
      setOfflineSaved(null);
      setResult(match.result);
    }
  }, [lastSynced, offlineSaved]);

  // A background flush DROPPED this page's offline capture (409/422): the "will
  // send automatically" promise no longer holds, so leave the saved-on-device
  // state — the refusal notice (syncNotices) becomes the primary message.
  useEffect(() => {
    if (offlineSaved === null) {
      return;
    }
    const droppedHere = lastDropped.some(
      (d) =>
        d.entry.check_in_date === offlineSaved.check_in_date &&
        d.entry.queued_at === offlineSaved.queued_at,
    );
    if (droppedHere) {
      setOfflineSaved(null);
    }
  }, [lastDropped, offlineSaved]);

  const functionComplete =
    answers.walking !== null && answers.stairs !== null && answers.balance_confidence !== null;
  // When symptom capture is on, both symptom items must be answered too.
  const symptomsComplete = symptoms.pain !== null && symptoms.numbness !== null;
  const complete = functionComplete && (!symptomsOn || symptomsComplete);

  const submit = async () => {
    if (
      answers.walking === null ||
      answers.stairs === null ||
      answers.balance_confidence === null
    ) {
      return;
    }
    // The patient's local calendar day — otherwise the backend defaults
    // to today-UTC and evening check-ins west of UTC land on tomorrow.
    const day = localCheckInDate();
    // Typed as the queue entry so it feeds both postAdlCheckIn and enqueueCheckIn; the
    // optional symptom fields are structurally compatible with AdlCheckInIn.
    const body: Omit<QueuedCheckIn, 'queued_at'> = {
      walking: answers.walking,
      stairs: answers.stairs,
      balance_confidence: answers.balance_confidence,
      check_in_date: day,
    };
    // Attach the symptom answers only when the feature is on AND both are set — the
    // server ignores them when off, but sending nothing keeps the payload honest.
    if (symptomsOn && symptoms.pain !== null && symptoms.numbness !== null) {
      body.pain = symptoms.pain;
      body.numbness = symptoms.numbness;
    }
    setSubmitting(true);
    setError(null);
    setFeatureOff(false);
    try {
      const saved = await postAdlCheckIn(body);
      // These newer answers supersede any same-day entry still queued on-device
      // (ADR-0006 semantics: only the newest same-day check-in counts) — and the
      // network clearly works, so flush any older queued days now. If a flush
      // pass is already mid-flight it iterates a stale snapshot, so this call
      // queues a FRESH pass (offlineSync's rerun) — the removal above is seen
      // and no older day is skipped.
      if (ownerId !== null) {
        removeQueuedCheckIn(ownerId, day);
        void flushQueuedCheckIns(ownerId);
      }
      setQueuedToday(null);
      setResult(saved);
    } catch (cause) {
      if (cause instanceof ApiError) {
        // API errors (4xx/5xx) keep their existing verbatim handling — only a
        // network-level failure is queued.
        if (cause.status === 409) {
          setFeatureOff(true);
          setError(cause.detail);
        } else {
          setError(messageFor(cause));
        }
      } else if (cause instanceof TypeError) {
        // fetch rejects with a TypeError when the network is unreachable — the
        // offline case (ADR-0030). Capture on-device, bound to this account.
        const queued = ownerId === null ? null : enqueueCheckIn(ownerId, body);
        if (queued !== null) {
          setOfflineSaved(queued);
          setQueuedToday(queued);
        } else {
          setError(messageFor(cause));
        }
      } else {
        setError(messageFor(cause));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const notices = syncNotices.map((notice) => (
    <ErrorNotice key={notice.id}>{notice.text}</ErrorNotice>
  ));

  // Wait for the capability read to resolve before rendering the form (like other
  // screens await their first read). Without this, a slow read would default the
  // symptom items OFF and a symptoms-on patient could submit a function-only check-in
  // without ever seeing the symptom section (ADR-0034). A failed read leaves
  // `capabilityLoading` false, so offline/error still proceeds function-only — only an
  // in-flight read blocks here.
  if (capabilityLoading && capabilityData === null) {
    return <Loading label="Loading your check-in…" />;
  }

  if (offlineSaved !== null) {
    return (
      <div>
        <h1>Check-in saved on this device</h1>
        {notices}
        <SuccessNotice>
          Saved on this device — will send automatically when you&apos;re back online.
        </SuccessNotice>
        <Link className="btn" to="/">
          Back to Home
        </Link>
      </div>
    );
  }

  if (result !== null) {
    return (
      <div>
        <h1>Check-in saved</h1>
        {notices}
        <SuccessNotice>
          Today&apos;s function score: <b>{result.daily_score} of 12</b>.
          {result.superseded && (
            <>
              {' '}
              This replaces the check-in you already did today — only the newest one counts in your
              trend.
            </>
          )}
        </SuccessNotice>
        <Link className="btn" to="/">
          Back to Home
        </Link>
        <Link className="btn ghost" to="/trends">
          See your trends
        </Link>
      </div>
    );
  }

  return (
    <div>
      <h1>Today&apos;s check-in</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Three quick questions about your day. 0 is the hardest, 4 is the easiest.
      </p>
      {notices}
      {queuedToday !== null && (
        <SuccessNotice>
          A check-in from today is saved on this device, waiting to send: walking{' '}
          {queuedToday.walking}, stairs {queuedToday.stairs}, balance{' '}
          {queuedToday.balance_confidence}. Submitting again replaces it.
        </SuccessNotice>
      )}
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
      <div className="card">
        {QUESTIONS.map((question) => (
          <SegmentedAnswer
            key={question.key}
            question={question}
            value={answers[question.key]}
            onChange={(answer) => {
              setAnswers((current) => ({ ...current, [question.key]: answer }));
            }}
          />
        ))}
      </div>
      {symptomsOn && (
        <>
          <h2>Symptoms today</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            For these, a higher number means it was worse. 0 means none.
          </p>
          <div className="card">
            {SYMPTOM_QUESTIONS.map((question) => (
              <SegmentedAnswer
                key={question.key}
                question={question}
                value={symptoms[question.key]}
                onChange={(answer) => {
                  setSymptoms((current) => ({ ...current, [question.key]: answer }));
                }}
              />
            ))}
          </div>
        </>
      )}
      <button
        className="btn"
        type="button"
        disabled={!complete || submitting}
        onClick={() => {
          void submit();
        }}
      >
        {submitting ? 'Saving…' : 'Save my check-in'}
      </button>
    </div>
  );
}
