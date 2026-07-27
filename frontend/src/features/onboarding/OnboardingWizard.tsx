/**
 * First-run welcome wizard (ADR-0044) — a short, focused, ACCESSIBLE (ADR-0039) intro shown
 * once to a new patient before the tabbed app.
 *
 * Rendered full-screen by the PatientArea gate (App.tsx) — its OWN app-frame/status-bar/
 * app-body frame (like InfoLayout) WITHOUT the bottom tab bar, so first-run is a single
 * focused flow. Reuses only existing primitives (card / eyebrow / muted / btn / pill /
 * disclaimer) so it introduces no new text-on-fill pair (no contrast-test additions) and
 * every control is already ≥ the 48px touch target. PHI-free and non-diagnostic: it explains
 * the app, it does not show or compute any health data. Finishing (or skipping) persists the
 * per-user flag and calls onComplete so the gate re-renders into the app.
 */

import { useState } from 'react';
import { markOnboardingComplete } from './onboardingState';

interface Step {
  eyebrow: string;
  title: string;
  lead: string;
  points: string[];
}

const STEPS: Step[] = [
  {
    eyebrow: 'Welcome',
    title: 'A clearer picture, over time',
    lead: 'This app helps you and your care team see how your nerves, balance, and daily activity are trending — gently, week to week.',
    points: [
      'You add a little; it shows the trend.',
      'Everything is optional — your app, your way.',
    ],
  },
  {
    eyebrow: 'How you add information',
    title: 'Three easy ways',
    lead: 'Pick whatever fits. You can start with just one and add more later.',
    points: [
      'A quick daily check-in — a few taps on your pain, numbness, and how you’re moving. Prefer not to be asked about pain and numbness? You can turn those off under Sources.',
      'Connect your health records to bring in your labs — you sign in on your provider’s own page.',
      'Upload a BioMech balance or gait report as a PDF.',
    ],
  },
  {
    eyebrow: 'Built for you',
    title: 'Easy to use, and yours',
    lead: 'Large text, big buttons, and check-ins that work even without a signal.',
    points: [
      'Turn any source on or off anytime under Sources.',
      'You can download or delete your data whenever you want.',
    ],
  },
];

export function OnboardingWizard({
  userId,
  onComplete,
}: {
  userId: string;
  onComplete: () => void;
}) {
  const [index, setIndex] = useState(0);
  const step = STEPS[index];
  const isLast = index === STEPS.length - 1;

  const finish = () => {
    markOnboardingComplete(userId);
    onComplete();
  };

  // index is always clamped within range; this narrows the type for the strict indexer.
  if (step === undefined) {
    return null;
  }

  return (
    <div className="app-frame">
      <header className="status-bar">
        <span className="mark">◍ Neuropathy</span>
        <button
          type="button"
          className="link"
          onClick={finish}
          style={{ color: 'var(--color-text-on-dark)' }}
        >
          Skip for now
        </button>
      </header>
      <main className="app-body" aria-label="Welcome">
        <div className="card">
          <div className="eyebrow">{step.eyebrow}</div>
          <h1>{step.title}</h1>
          <p className="muted" style={{ marginTop: 0 }}>
            {step.lead}
          </p>
          <ul style={{ paddingLeft: 'var(--space-lg)', margin: 0 }}>
            {step.points.map((point) => (
              <li key={point} style={{ marginBottom: 'var(--space-sm)' }}>
                {point}
              </li>
            ))}
          </ul>
        </div>

        {isLast && (
          <p className="disclaimer" role="note">
            This app helps you track and understand your information. It does not diagnose, treat,
            or prevent any disease, and it is not a substitute for professional medical advice.
          </p>
        )}

        {/* Progress — plain text carries the state (never color alone, ADR-0039). */}
        <p className="muted centered" aria-live="polite">
          Step {index + 1} of {STEPS.length}
        </p>

        {isLast ? (
          <button type="button" className="btn" onClick={finish}>
            Get started
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setIndex((current) => Math.min(current + 1, STEPS.length - 1));
            }}
          >
            Next
          </button>
        )}
        {index > 0 && (
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              setIndex((current) => Math.max(current - 1, 0));
            }}
          >
            Back
          </button>
        )}
      </main>
    </div>
  );
}
