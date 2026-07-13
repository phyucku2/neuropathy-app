/**
 * Home — the trajectory answer, up top (mockup screen 1): the gradient hero
 * card with direction / plain-language summary / confidence, the sourced
 * signal list, and an explicit data-gaps card.
 */

import { Link } from 'react-router-dom';
import { getTrajectory } from '../../api/endpoints';
import type { Direction, SignalTrend } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { labelFor, sourceLabel } from '../../lib/signalMeta';
import { useApi } from '../../lib/useApi';

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

function SignalRow({ signal }: { signal: SignalTrend }) {
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

export function HomePage() {
  const { data: trajectory, error, loading } = useApi(getTrajectory);

  if (loading) {
    return <Loading label="Working out your trend…" />;
  }
  if (error !== null || trajectory === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  const percent = Math.round(trajectory.confidence * 100);

  return (
    <div>
      <section className={`traj ${trajectory.direction}`} aria-label="Your 30-day trend">
        <div className="eyebrow">Your 30-day trend</div>
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

      {trajectory.signals.length > 0 && (
        <div className="card">
          <div className="eyebrow">What&apos;s driving it</div>
          {trajectory.signals.map((signal) => (
            <SignalRow key={`${signal.source}:${signal.code}`} signal={signal} />
          ))}
        </div>
      )}

      {trajectory.data_gaps.length > 0 && (
        <div className="card">
          <div className="eyebrow">Data gaps</div>
          <ul className="muted" style={{ margin: 0, paddingLeft: 20 }}>
            {trajectory.data_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </div>
      )}

      <Link className="btn" to="/check-in">
        Today&apos;s check-in · 3 questions
      </Link>
      <Link className="btn ghost" to="/trends">
        See your trends
      </Link>
      <p className="muted centered" style={{ marginTop: 10 }}>
        Not medical advice. Share with your care team.
      </p>
    </div>
  );
}
