/**
 * Home — the trajectory answer, up top (mockup screen 1): the gradient hero
 * card with direction / plain-language summary / confidence, the sourced
 * signal list, and an explicit data-gaps card.
 */

import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { getTrajectory } from '../../api/endpoints';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { SignalRow, TrajectoryHero } from '../../components/TrajectoryView';
import { firstName } from '../../lib/format';
import { useApi } from '../../lib/useApi';

export function HomePage() {
  const { user } = useAuth();
  const { data: trajectory, error, loading } = useApi(getTrajectory);
  const greetingName = firstName(user?.display_name ?? '');

  if (loading) {
    return <Loading label="Working out your trend…" />;
  }
  if (error !== null || trajectory === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  // No signals yet = a brand-new account with nothing ingested. Drive onboarding into that
  // space instead of leaving it blank (below).
  const hasData = trajectory.signals.length > 0;

  return (
    <div>
      <h1 className="greeting">{greetingName ? `Hi, ${greetingName}` : 'Welcome back'}</h1>
      <TrajectoryHero
        trajectory={trajectory}
        eyebrow="30 Day Score"
        ariaLabel="Your 30 day score"
      />
      {/* Non-diagnostic note CO-LOCATED with the computed direction (ADR-0016/0041): every
          surface that shows a direction carries the disclaimer right beside it, not only in
          the footer. */}
      <p className="disclaimer" role="note">
        This is a wellness trend, not a diagnosis. Share it with your care team.
      </p>

      {hasData && (
        <div className="card">
          <div className="eyebrow">What&apos;s driving it</div>
          {trajectory.signals.map((signal) => (
            <SignalRow key={`${signal.source}:${signal.code}`} signal={signal} />
          ))}
        </div>
      )}

      {/* Empty state (no signals yet): turn the dead space below the hero into onboarding —
          three concrete first steps, big tappable rows for the 60+ audience (ADR-0039) —
          rather than a blank screen. */}
      {!hasData && (
        <section className="card" aria-labelledby="get-started-heading">
          <div className="eyebrow" id="get-started-heading">
            Get started
          </div>
          <p className="muted" style={{ marginTop: 0 }}>
            Three ways to add your first data — your trend appears here once you do.
          </p>
          <Link className="btn ghost" to="/check-in">
            1 · Do today&apos;s check-in
          </Link>
          <Link className="btn ghost" to="/settings">
            2 · Connect your health record
          </Link>
          <Link className="btn ghost" to="/add">
            3 · Add a lab or report
          </Link>
        </section>
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

      {/* With data, the primary actions live at the bottom. In the empty state they'd be
          redundant with the Get-started card (check-in) or pointless ("See your trends"
          with no trend), so they're hidden there. */}
      {hasData && (
        <>
          <Link className="btn" to="/check-in">
            Today&apos;s check-in · 3 questions
          </Link>
          <Link className="btn ghost" to="/trends">
            See your trends
          </Link>
        </>
      )}
      <p className="muted centered" style={{ marginTop: 10 }}>
        Not medical advice. Share with your care team.
      </p>
    </div>
  );
}
