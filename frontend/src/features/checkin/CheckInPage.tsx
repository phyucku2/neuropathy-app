/**
 * Daily check-in — the three 0-4 ADL questions as the mockup's segmented
 * buttons. POST /adl; a same-day re-submission shows the superseded notice;
 * a 409 means the feature is turned off (server-enforced toggle, ADR-0013).
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, messageFor } from '../../api/client';
import { postAdlCheckIn } from '../../api/endpoints';
import type { AdlCheckInOut } from '../../api/types';
import { ErrorNotice, SuccessNotice } from '../../components/StatusMessages';

const ANSWER_VALUES = [0, 1, 2, 3, 4] as const;

interface Question {
  key: 'walking' | 'stairs' | 'balance_confidence';
  prompt: string;
  low: string;
  high: string;
}

const QUESTIONS: Question[] = [
  { key: 'walking', prompt: 'How did walking feel today?', low: 'Very hard', high: 'Easy' },
  { key: 'stairs', prompt: 'How were stairs today?', low: 'Very hard', high: 'Easy' },
  {
    key: 'balance_confidence',
    prompt: 'How confident did you feel about your balance?',
    low: 'Not confident',
    high: 'Very confident',
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
  return (
    <fieldset className="seg-group">
      <legend>{question.prompt}</legend>
      <div className="seg-row" role="radiogroup" aria-label={question.prompt}>
        {ANSWER_VALUES.map((answer) => (
          <button
            key={answer}
            type="button"
            className="seg"
            role="radio"
            aria-checked={value === answer}
            onClick={() => {
              onChange(answer);
            }}
          >
            {answer}
          </button>
        ))}
      </div>
      <div className="seg-anchors" aria-hidden="true">
        <span>0 · {question.low}</span>
        <span>4 · {question.high}</span>
      </div>
    </fieldset>
  );
}

export function CheckInPage() {
  const [answers, setAnswers] = useState<Record<Question['key'], number | null>>({
    walking: null,
    stairs: null,
    balance_confidence: null,
  });
  const [result, setResult] = useState<AdlCheckInOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [featureOff, setFeatureOff] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const complete =
    answers.walking !== null && answers.stairs !== null && answers.balance_confidence !== null;

  const submit = async () => {
    if (
      answers.walking === null ||
      answers.stairs === null ||
      answers.balance_confidence === null
    ) {
      return;
    }
    setSubmitting(true);
    setError(null);
    setFeatureOff(false);
    try {
      setResult(
        await postAdlCheckIn({
          walking: answers.walking,
          stairs: answers.stairs,
          balance_confidence: answers.balance_confidence,
        }),
      );
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setFeatureOff(true);
        setError(cause.detail);
      } else {
        setError(messageFor(cause));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (result !== null) {
    return (
      <div>
        <h1>Check-in saved</h1>
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
