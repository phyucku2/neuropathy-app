/**
 * The Learn module registry (ADR-0037).
 *
 * A CLOSED, authored, in-app list — NOT server data. Like the metric / directionality
 * registries, the education modules are static and versioned in code; there is no runtime
 * generation of medical content (a hallucinated foot-care instruction is unacceptable —
 * ADR-0037). These entries are PLACEHOLDERS: the narrated-slideshow content, the opt-in
 * capability, and PHI-free progress tracking are all FUTURE backend work, so nothing here
 * needs a server capability yet and nothing is clickable-into.
 *
 * Ordering is deliberate and evidence-first: exercise / balance training LEADS because it
 * is the only module with strong VERIFIED outcome evidence in DPN (2025 meta-analysis:
 * gait speed +0.08 m/s, strength SMD 0.76 — see docs/product/dpn-adl-falls-and-education-
 * evidence.md). Every module is general disease education for everyone, never advice
 * tailored to the individual's readings (the non-diagnostic line, ADR-0037).
 */

/** A placeholder review/availability state (both are FUTURE — no content ships yet). */
export type ModuleStatus = 'reviewed' | 'coming-soon';

export interface LearnModule {
  /** Stable id (also the future progress-store key — PHI-free counts/ids only). */
  id: string;
  /** A single glyph, paired ALWAYS with the title text — never color/icon alone (ADR-0039). */
  icon: string;
  /** Plain-language module title. */
  title: string;
  /** One line, 6th–8th-grade reading level — what the module is about. */
  blurb: string;
  /** Placeholder state badge; carries its own words, so it never relies on color alone. */
  status: ModuleStatus;
  /** The evidence-first lead module gets the prominent "Next session" treatment. */
  featured?: boolean;
}

export const LEARN_MODULES: LearnModule[] = [
  {
    id: 'exercise-balance',
    icon: '🏃',
    title: 'Exercise & balance training',
    blurb: 'Simple moves to build strength and steady your balance, a little each day.',
    // The evidence-first lead (ADR-0037): reviewed-state placeholder + "Next session" style.
    status: 'reviewed',
    featured: true,
  },
  {
    id: 'foot-care',
    icon: '🦶',
    title: 'Foot care',
    blurb: 'How to check your feet every day and catch small problems early.',
    status: 'coming-soon',
  },
  {
    id: 'glycemic-control',
    icon: '🩸',
    title: 'Glycemic control basics',
    blurb: 'What blood sugar is and why keeping it steady helps your nerves.',
    status: 'coming-soon',
  },
  {
    id: 'fall-prevention',
    icon: '🏠',
    title: 'Fall prevention & home safety',
    blurb: 'Easy changes at home that lower your chance of a fall.',
    status: 'coming-soon',
  },
  {
    id: 'nerve-pain',
    icon: '⚡',
    title: 'Managing nerve pain',
    blurb: 'Ways to ease burning, tingling, and pain from nerve damage.',
    status: 'coming-soon',
  },
  {
    id: 'footwear-nail-care',
    icon: '👟',
    title: 'Footwear & nail care',
    blurb: 'Picking shoes that fit and caring for your toenails the safe way.',
    status: 'coming-soon',
  },
  {
    id: 'nutrition',
    icon: '🥗',
    title: 'Nutrition basics',
    blurb: 'Everyday food choices that support your blood sugar and your health.',
    status: 'coming-soon',
  },
  {
    id: 'when-to-call',
    icon: '📞',
    title: 'When to call your care team',
    blurb: 'The warning signs that mean you should reach out right away.',
    status: 'coming-soon',
  },
];
