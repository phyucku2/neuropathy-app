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

  return (
    <div>
      <h1 className="greeting">{greetingName ? `Hi, ${greetingName}` : 'Welcome back'}</h1>
      <TrajectoryHero
        trajectory={trajectory}
        eyebrow="Your 30-day trend"
        ariaLabel="Your 30-day trend"
      />

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
