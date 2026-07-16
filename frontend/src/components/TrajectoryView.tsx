/**
 * Shared trajectory presentation: the number-forward Neuropathy Status Index
 * hero card (ADR-0034) and the sourced signal rows. Used by the patient Home
 * screen and the clinician patient view — the SAME deterministic computation
 * rendered for two audiences (ADR-0012), so the two presentations can never drift.
 *
 * The hero shows the 0-100 Index, its OWN 30-day delta, a Confidence chip, and the
 * `as_of` date. The card colour AND the arrow are both driven by `score_delta_30d`,
 * so they can never contradict (the ADR retires the old multi-signal direction vote
 * on this surface). Direction is conveyed in WORDS + a glyph, never colour alone
 * (WCAG 1.4.1), and the section's accessible name speaks score + direction + delta +
 * `as_of` + Confidence together.
 */

import type { ConfidenceLevel, SignalTrend, Trajectory } from '../api/types';
import { formatDay } from '../lib/format';
import { labelFor, sourceLabel } from '../lib/signalMeta';

/** The card's visual + spoken state, derived ENTIRELY from `score_delta_30d` so the
 *  gradient class, the arrow glyph, and the direction word can never disagree. */
type NsiDirection = 'improving' | 'declining' | 'steady';

const DIRECTION: Record<NsiDirection, { cls: string; glyph: string; word: string }> = {
  improving: { cls: 'improving', glyph: '↑', word: 'improving' },
  declining: { cls: 'declining', glyph: '↓', word: 'declining' },
  steady: { cls: 'stable', glyph: '→', word: 'steady' },
};

const CONFIDENCE_WORD: Record<ConfidenceLevel, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

function nsiDirection(delta: number): NsiDirection {
  if (delta > 0) return 'improving';
  if (delta < 0) return 'declining';
  return 'steady';
}

/** "+7" / "−7" / "0" — signed point difference, using a real minus glyph. */
function signedPoints(delta: number): string {
  if (delta > 0) return `+${String(delta)}`;
  if (delta < 0) return `−${String(Math.abs(delta))}`;
  return '0';
}

const SOURCE_ICONS: Record<string, { glyph: string; color: string }> = {
  biomech: { glyph: '◔', color: 'var(--color-brand-blue)' },
  adl: { glyph: '☑', color: 'var(--color-action-green)' },
  lab: { glyph: '⚗', color: 'var(--color-status-warning)' },
  emr: { glyph: '🏥', color: 'var(--color-brand-sky)' },
};

export function SignalRow({ signal }: { signal: SignalTrend }) {
  const icon = SOURCE_ICONS[signal.source] ?? {
    glyph: '•',
    color: 'var(--color-status-neutral)',
  };
  // 'insufficient_data' must never fall into the 'stable' branch: the backend
  // explicitly refuses to judge these signals, so the UI must not fabricate a
  // stability claim (visually or in the aria-label).
  const arrow =
    signal.direction === 'improving'
      ? { glyph: '↑', className: 'arrow up', text: 'improving' }
      : signal.direction === 'declining'
        ? { glyph: '↓', className: 'arrow down', text: 'declining' }
        : signal.direction === 'stable'
          ? { glyph: '→', className: 'arrow flat', text: 'stable' }
          : { glyph: '·', className: 'arrow unjudged', text: 'not enough data' };
  return (
    <div className="signal">
      <span className="dot" style={{ background: icon.color }} aria-hidden="true">
        {icon.glyph}
      </span>
      <div className="t">
        <b>{labelFor(signal.code)}</b> <span className="chip">{sourceLabel(signal.source)}</span>
        <br />
        <span className="muted">{signal.detail}</span>
      </div>
      <span className={arrow.className} role="img" aria-label={arrow.text}>
        {arrow.glyph}
      </span>
    </div>
  );
}

export function TrajectoryHero({
  trajectory,
  eyebrow,
  ariaLabel,
}: {
  trajectory: Trajectory;
  eyebrow: string;
  /** Caller context prefix (e.g. "Your 30 day score" / "30 day score for Pat Example").
   *  The section's full accessible name appends the spoken score + direction + delta +
   *  as_of + Confidence to this prefix. */
  ariaLabel: string;
}) {
  const { score, score_delta_30d, as_of, confidence_level, data_is_stale } = trajectory;

  // No composite yet: the honest "not enough data" state (unchanged treatment).
  if (score === null) {
    return (
      <section className="traj insufficient_data" aria-label={`${ariaLabel}: not enough data yet`}>
        <div className="eyebrow">{eyebrow}</div>
        <div className="answer">Not enough data yet</div>
        <div className="sub">Add a check-in, report, or lab and your score will appear here.</div>
      </section>
    );
  }

  const delta = score_delta_30d ?? 0;
  const dir = DIRECTION[nsiDirection(delta)];
  const asOfText = as_of === null ? null : formatDay(Date.parse(as_of));
  const confidenceWord = confidence_level === null ? null : CONFIDENCE_WORD[confidence_level];

  // The section's accessible name says everything the visual conveys, in one breath.
  const spoken = [
    `${ariaLabel}: score ${String(score)} out of 100`,
    dir.word,
    `${signedPoints(delta)} points vs 30 days ago`,
    asOfText === null ? null : `as of ${asOfText}`,
    confidenceWord === null ? null : `confidence ${confidenceWord.toLowerCase()}`,
    data_is_stale ? 'data may be out of date' : null,
  ]
    .filter((part) => part !== null)
    .join(', ');

  return (
    <section className={`traj ${dir.cls}`} aria-label={spoken}>
      <div className="eyebrow">{eyebrow}</div>
      <div className="score" aria-hidden="true">
        <span className="score-num">{score}</span>
        <span className="score-unit">/100</span>
      </div>
      {/* Direction in WORDS + a glyph — never colour alone (WCAG 1.4.1). */}
      <div className="dirline" aria-hidden="true">
        <span className={`nsi-arrow ${dir.cls}`}>{dir.glyph}</span>
        <span className="dirword">{dir.word}</span>
      </div>
      <div className="delta" aria-hidden="true">
        <b>{signedPoints(delta)} pts</b> vs 30 days ago
      </div>
      <div className="nsi-foot" aria-hidden="true">
        {confidenceWord !== null && <span className="conf-chip">Confidence: {confidenceWord}</span>}
        {asOfText !== null && (
          <span className="asof">
            as of {asOfText}
            {data_is_stale && ' · may be out of date'}
          </span>
        )}
      </div>
    </section>
  );
}
