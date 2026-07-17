/**
 * Learn — the non-diagnostic education-module index (ADR-0037), built to the 60+
 * accessibility bar (ADR-0039): large legible type, strong-contrast tokens, generous
 * spacing, one purpose per card, and no color-only meaning (every state carries words).
 *
 * The module list comes from the LOCAL closed registry (./modules), never the server —
 * v1 is general disease education for everyone, and opt-in / progress tracking is FUTURE
 * backend work (ADR-0037). So this page makes NO data calls: the cards are placeholders,
 * nothing is clickable-into yet, and each carries a clearly-labeled empty video slot where
 * a narrated slideshow will later embed. The page ends with the standard non-diagnostic
 * disclaimer that ADR-0037 requires on every Learn surface.
 */

import { LEARN_MODULES, type LearnModule } from './modules';

// The standard non-diagnostic disclaimer for the Learn surface (ADR-0037). Kept as a
// literal here — the wording is the "general education, not advice" posture and must not
// drift into anything that reads as individualized medical direction.
const NON_DIAGNOSTIC_TEXT = 'General education — not medical advice. Talk to your care team.';

function ModuleCard({ module }: { module: LearnModule }) {
  const reviewed = module.status === 'reviewed';
  // The status is a placeholder (no content ships yet, ADR-0037); the pill always carries
  // its own words, so meaning never rides on color alone (ADR-0039 / WCAG 1.4.1).
  const statusLabel = reviewed ? 'Reviewed by your care team' : 'Coming soon';
  // The featured (evidence-first) lead gets the prominent "Next session" affordance; the
  // rest show a plainly-labeled "coming soon" player slot. Neither is clickable yet.
  const videoLabel = module.featured ? 'Next session ▶' : '▶ Watch (coming soon)';

  return (
    <article className={module.featured ? 'card learn-card featured' : 'card learn-card'}>
      <div className="learn-head">
        <span className="learn-ic" aria-hidden="true">
          {module.icon}
        </span>
        <div className="learn-titles">
          <h2>{module.title}</h2>
          <span className={reviewed ? 'pill on' : 'pill off'}>{statusLabel}</span>
        </div>
      </div>
      <p className="muted learn-blurb">{module.blurb}</p>
      {/* Video slot placeholder: a clearly-labeled empty player area (no real player yet).
          Not a button — nothing plays, so it stays non-interactive rather than being a
          control that does nothing. The ▶ glyph is decorative; the words carry the state. */}
      <div className="video-slot">
        <span className="video-cta">{videoLabel}</span>
      </div>
    </article>
  );
}

export function LearnPage() {
  return (
    <div>
      <h1>Learn</h1>
      <p className="muted learn-intro">
        Short, plain-language lessons on living well with neuropathy. General health education — new
        lessons are on the way.
      </p>

      {LEARN_MODULES.map((module) => (
        <ModuleCard key={module.id} module={module} />
      ))}

      <p className="disclaimer" role="note">
        {NON_DIAGNOSTIC_TEXT}
      </p>
    </div>
  );
}
