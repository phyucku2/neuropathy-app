/**
 * First-run onboarding state (ADR-0044) — a client-side "this patient has seen the welcome
 * wizard" flag.
 *
 * Storage is `localStorage`, keyed with the app's `neuropathy.*` naming (mirrors
 * native/reminders.ts and emr/pendingConnect.ts). It is a DEVICE preference, not PHI: a JSON
 * array of the `user_id`s that have finished onboarding — keyed by user so a shared browser
 * doesn't suppress the wizard for a second patient (the same per-owner concern the token
 * store and offline queue already handle). It intentionally OUTLIVES logout (a returning user
 * shouldn't re-see the wizard), exactly like the reminder preference. Corrupt/absent entries
 * read as "not yet onboarded" — fail toward showing the welcome, never toward hiding it.
 */

export const ONBOARDING_COMPLETE_KEY = 'neuropathy.onboarding_complete';

function readCompletedIds(): string[] {
  // The WHOLE read is guarded: `localStorage.getItem` itself throws in some browsers
  // (Safari Private Mode, storage disabled) — not just `JSON.parse`. A throwing store must
  // read as "nobody onboarded yet" so the gate FAILS TOWARD SHOWING the welcome, never
  // toward a white screen.
  try {
    const raw = localStorage.getItem(ONBOARDING_COMPLETE_KEY);
    if (raw === null) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((id) => typeof id === 'string')) {
      return parsed as string[];
    }
  } catch {
    // Unreadable/absent store — treat as "not yet onboarded"; the wizard simply shows again.
  }
  return [];
}

export function isOnboardingComplete(userId: string): boolean {
  return readCompletedIds().includes(userId);
}

export function markOnboardingComplete(userId: string): void {
  const ids = readCompletedIds();
  if (ids.includes(userId)) {
    return;
  }
  try {
    localStorage.setItem(ONBOARDING_COMPLETE_KEY, JSON.stringify([...ids, userId]));
  } catch {
    // A throwing/full store can't persist the flag — the wizard reappears next launch, which
    // is a harmless degradation (never a crash). Nothing else to do.
  }
}
