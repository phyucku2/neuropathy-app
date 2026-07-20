/**
 * The fixed Visit-Ready Summary windows (ADR-0045), mirrored from the backend's
 * ALLOWED_WINDOW_DAYS / DEFAULT_WINDOW_DAYS (backend/app/schemas/visit_summary.py). The
 * backend validates the query param against this exact set (422 otherwise), so the picker only
 * ever offers these — a value outside the set can never be requested from the UI.
 */

export const ALLOWED_WINDOW_DAYS = [30, 60, 90, 120, 365] as const;

export const DEFAULT_WINDOW_DAYS = 60;

/** Plain-language window name for the picker + headings (365 reads as "1 year", 60+ friendly). */
export function windowLabel(days: number): string {
  return days === 365 ? '1 year' : `${String(days)} days`;
}
