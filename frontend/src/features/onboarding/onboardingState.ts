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
  const raw = localStorage.getItem(ONBOARDING_COMPLETE_KEY);
  if (raw === null) {
    return [];
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((id) => typeof id === 'string')) {
      return parsed as string[];
    }
  } catch {
    // Corrupt entry — treat as "nobody onboarded yet"; the wizard simply shows again.
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
  localStorage.setItem(ONBOARDING_COMPLETE_KEY, JSON.stringify([...ids, userId]));
}
