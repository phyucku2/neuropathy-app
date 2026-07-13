/**
 * Shared trajectory presentation: the gradient hero card (direction /
 * plain-language summary / confidence) and the sourced signal rows. Used by
 * the patient Home screen and the clinician patient view — the SAME
 * deterministic computation rendered for two audiences (ADR-0012), so the two
 * presentations can never drift.
 */

import type { Direction, SignalTrend, Trajectory } from '../api/types';
import { labelFor, sourceLabel } from '../lib/signalMeta';

const ANSWERS: Record<Direction, string> = {
  improving: 'Improving',
  stable: 'Stable',
  declining: 'Declining',
  insufficient_data: 'Not enough data yet',
};

function confidenceWord(confidence: number): string {
  if (confidence >= 0.7) return 'Good';
  if (confidence >= 0.4) return 'Fair';
  return 'Low';
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
  ariaLabel: string;
}) {
  const percent = Math.round(trajectory.confidence * 100);
  return (
    <section className={`traj ${trajectory.direction}`} aria-label={ariaLabel}>
      <div className="eyebrow">{eyebrow}</div>
      <div className="answer">{ANSWERS[trajectory.direction]}</div>
      <div className="sub">{trajectory.summary}</div>
      <div className="conf">
        <span>Confidence</span>
        <span className="cbar" role="img" aria-label={`Confidence ${String(percent)} percent`}>
          <i style={{ width: `${String(percent)}%` }} />
        </span>
        <span>{confidenceWord(trajectory.confidence)}</span>
      </div>
      {trajectory.narrative_source === 'ai' && (
        <span className="ai-badge">✦ AI-written summary — numbers computed from your data</span>
      )}
    </section>
  );
}
