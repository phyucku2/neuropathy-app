/**
 * Shared plain-language metadata for the caregiver alert types (ADR-0047 B1).
 *
 * One source of truth for the display order + 60+ friendly label and description of each
 * `CaregiverAlertType`, used by BOTH the caregiver Alerts feed (the icon/label beside an
 * alert) and the patient's per-type opt-in card (the toggle rows). The alert BODY copy
 * itself is fixed by the backend (non-diagnostic template constants); these strings only
 * name the category in the UI chrome, never diagnose.
 */

import type { CaregiverAlertType } from '../../api/types';

/** The canonical display order (matches the backend enum order). */
export const ALERT_TYPE_ORDER: CaregiverAlertType[] = [
  'missed_checkin',
  'med_change',
  'trend_shift',
  'new_chart_note',
];

export interface AlertTypeMeta {
  /** A short, non-diagnostic category name for a 60+ surface. */
  label: string;
  /** One plain sentence, phrased from the patient's point of view (opt-in card). */
  description: string;
  /** A decorative glyph + its verified background token (reused from Sources icons). */
  glyph: string;
  color: string;
}

export const ALERT_TYPE_META: Record<CaregiverAlertType, AlertTypeMeta> = {
  missed_checkin: {
    label: 'Missed daily check-ins',
    description: "Tell them when a daily check-in hasn't happened in a while.",
    glyph: '☑',
    color: 'var(--color-action-green)',
  },
  med_change: {
    label: 'Medication updates',
    description: 'Tell them when your medication list changes.',
    glyph: '✚',
    color: 'var(--color-status-warning)',
  },
  trend_shift: {
    label: 'Wellness trend shifts',
    description: 'Tell them when your weekly wellness trend changes direction.',
    glyph: '📈',
    color: 'var(--color-brand-sky)',
  },
  new_chart_note: {
    label: 'New notes from the care team',
    description: 'Tell them when a new note from a clinician is on file.',
    glyph: '📝',
    color: 'var(--color-brand-blue)',
  },
};
