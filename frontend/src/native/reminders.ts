/**
 * Daily check-in reminder (ADR-0029) — a patient-configurable local notification,
 * native-only (Android). Follows the nativeShell/externalBrowser seam pattern
 * (ADR-0024/0025): pure logic + an injectable plugin accessor, so every decision is
 * unit-testable off-device; jsdom is never the native platform, so the web build
 * never touches the plugin.
 *
 * The preference (enabled + time) is a DEVICE preference in `localStorage`, not
 * server state (ADR-0029): a reminder belongs to the phone it fires on — no server
 * round-trip, works offline, and two devices can legitimately want two different
 * times. It carries no PHI (a boolean and a wall-clock time).
 *
 * The notification content is FIXED and PHI-FREE by construction: the title/body
 * constants below are the only content ever scheduled — never any health data,
 * score, or name. Android shows notifications on the lock screen by default.
 */

import { LocalNotifications } from '@capacitor/local-notifications';
import { isNativePlatform } from '../auth/platform';

/** localStorage key, following the token store's `neuropathy.*` naming. */
export const REMINDER_PREF_KEY = 'neuropathy.checkin_reminder';

/**
 * Fixed notification id (Android: 32-bit int). Scheduling the SAME id replaces the
 * pending alarm (the plugin's Android PendingIntent uses FLAG_CANCEL_CURRENT), so
 * enable/re-enable/time-change never accumulates duplicate reminders.
 */
export const REMINDER_NOTIFICATION_ID = 20260715;

/** PHI-free, fixed content — the ONLY strings this app ever puts in a notification. */
export const REMINDER_TITLE = 'Daily check-in';
export const REMINDER_BODY = 'How are you feeling today? 30 seconds is all it takes.';

export const DEFAULT_REMINDER_HOUR = 9;
export const DEFAULT_REMINDER_MINUTE = 0;

export interface ReminderState {
  enabled: boolean;
  /** Local wall-clock hour, 0–23. */
  hour: number;
  /** Local wall-clock minute, 0–59. */
  minute: number;
}

/**
 * The slice of the LocalNotificationsPlugin the seam uses, injectable so unit tests
 * pass a fake instead of mocking the plugin across the import graph (ADR-0024
 * seam lesson). The real plugin satisfies this structurally.
 */
export interface ReminderPlugin {
  checkPermissions(): Promise<{ display: string }>;
  requestPermissions(): Promise<{ display: string }>;
  schedule(options: {
    notifications: {
      id: number;
      title: string;
      body: string;
      schedule: { on: { hour: number; minute: number }; allowWhileIdle: boolean };
    }[];
  }): Promise<unknown>;
  cancel(options: { notifications: { id: number }[] }): Promise<void>;
}

export type EnableReminderResult = 'scheduled' | 'permission-denied' | 'unavailable';

function isValidTime(hour: number, minute: number): boolean {
  return (
    Number.isInteger(hour) &&
    Number.isInteger(minute) &&
    hour >= 0 &&
    hour <= 23 &&
    minute >= 0 &&
    minute <= 59
  );
}

function persist(state: ReminderState): void {
  localStorage.setItem(REMINDER_PREF_KEY, JSON.stringify(state));
}

/**
 * The stored preference, or the disabled 09:00 default when nothing valid is stored.
 * A corrupt/out-of-range entry reads as the default (never a crash, never a bogus
 * schedule time).
 */
export function getReminderState(): ReminderState {
  const raw = localStorage.getItem(REMINDER_PREF_KEY);
  if (raw !== null) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (
        parsed !== null &&
        typeof parsed === 'object' &&
        typeof (parsed as ReminderState).enabled === 'boolean' &&
        isValidTime((parsed as ReminderState).hour, (parsed as ReminderState).minute)
      ) {
        const state = parsed as ReminderState;
        return { enabled: state.enabled, hour: state.hour, minute: state.minute };
      }
    } catch {
      // Corrupt entry — fall through to the default.
    }
  }
  return { enabled: false, hour: DEFAULT_REMINDER_HOUR, minute: DEFAULT_REMINDER_MINUTE };
}

/**
 * Ask permission and schedule the DAILY repeating reminder at the given local time.
 *
 * - `'scheduled'` — permission granted, alarm registered, preference persisted.
 * - `'permission-denied'` — the OS refused (Android 13+ runtime permission); nothing
 *   is scheduled and the preference stays off. This is a RESULT the UI renders as
 *   guidance (system-settings hint), never a throw — a denied prompt is a normal
 *   user choice, not an error.
 * - `'unavailable'` — web: local notifications only exist in the native shell; no-op.
 *
 * The `schedule.on {hour, minute}` form is the plugin's cron-like repeating schedule
 * (Cap-6 `Schedule.on` in definitions.d.ts): Android computes the next matching
 * wall-clock trigger and re-registers the following one after each fire — a daily
 * repeat that also survives the fire itself.
 *
 * HONEST DELIVERY LIMITS (ADR-0029): `allowWhileIdle` is requested but is
 * best-effort only. Without the SCHEDULE_EXACT_ALARM permission, Android 12+
 * schedules the first fire INEXACTLY (the OS may defer/batch it), and the plugin's
 * post-fire re-registration of the `on` schedule uses a plain non-wakeup alarm that
 * ignores `allowWhileIdle` — so from day 2 onward a dozing device may not show the
 * nudge until it next wakes. Net: the reminder arrives AROUND the chosen time, not
 * at it. Deliberately accepted for a daily wellness nudge; exact alarms are a
 * recorded non-adoption in ADR-0029.
 */
export async function enableReminder(
  hour: number,
  minute: number,
  plugin: ReminderPlugin = LocalNotifications,
): Promise<EnableReminderResult> {
  if (!isValidTime(hour, minute)) {
    throw new RangeError(`Invalid reminder time: ${String(hour)}:${String(minute)}`);
  }
  if (!isNativePlatform()) {
    return 'unavailable';
  }
  const permission = await plugin.requestPermissions();
  if (permission.display !== 'granted') {
    return 'permission-denied';
  }
  await plugin.schedule({
    notifications: [
      {
        id: REMINDER_NOTIFICATION_ID,
        title: REMINDER_TITLE,
        body: REMINDER_BODY,
        schedule: { on: { hour, minute }, allowWhileIdle: true },
      },
    ],
  });
  persist({ enabled: true, hour, minute });
  return 'scheduled';
}

/**
 * Cancel the scheduled reminder and persist the preference off. The chosen time is
 * KEPT so re-enabling restores it. On web there is nothing to cancel — the
 * preference alone is updated (kept consistent should storage sync to a device).
 */
export async function disableReminder(plugin: ReminderPlugin = LocalNotifications): Promise<void> {
  const current = getReminderState();
  persist({ ...current, enabled: false });
  if (!isNativePlatform()) {
    return;
  }
  await plugin.cancel({ notifications: [{ id: REMINDER_NOTIFICATION_ID }] });
}

/**
 * Best-effort reminder cleanup for ACCOUNT DELETION (the ADR-0027 danger-zone flow):
 * cancel the scheduled notification and REMOVE the stored preference entirely.
 * Unlike `disableReminder` (a user choice that keeps the chosen time for re-enable),
 * deletion leaves nothing behind — the account is gone, so this device must not keep
 * nudging for it, and the next signup on this device must not inherit the dead
 * account's preference.
 *
 * NEVER throws: account deletion must never fail (or appear to fail) because a
 * notification cancel faulted, so every error is swallowed. Plain LOGOUT deliberately
 * does NOT call this — the reminder is a device preference with fixed PHI-free
 * content (per-device semantics, ADR-0029), so it survives sign-out.
 */
export async function disableReminderSilently(
  plugin: ReminderPlugin = LocalNotifications,
): Promise<void> {
  try {
    localStorage.removeItem(REMINDER_PREF_KEY);
    if (isNativePlatform()) {
      await plugin.cancel({ notifications: [{ id: REMINDER_NOTIFICATION_ID }] });
    }
  } catch {
    // Swallowed by design — this cleanup is best-effort and must never block deletion.
  }
}

/**
 * Whether the OS notification permission is currently granted — `checkPermissions`
 * only, NEVER `requestPermissions`, so callers (e.g. the Settings card's mount probe
 * against a stored "enabled" preference the OS no longer honors) can ask without
 * ever popping a dialog. On web there is nothing to grant and no guidance to show,
 * so it reports true without touching the plugin.
 */
export async function isReminderPermissionGranted(
  plugin: ReminderPlugin = LocalNotifications,
): Promise<boolean> {
  if (!isNativePlatform()) {
    return true;
  }
  const permission = await plugin.checkPermissions();
  return permission.display === 'granted';
}

/**
 * Re-assert the reminder at app launch (called fire-and-forget from the native
 * shell init, AFTER the splash is hidden — ADR-0029). Some Android OEMs drop
 * scheduled alarms on reboot or app update; re-scheduling the same fixed id is
 * idempotent (replaces the pending alarm) and restores a dropped one.
 *
 * Uses `checkPermissions` — never `requestPermissions` — so a cold launch can never
 * pop a permission dialog. If permission was revoked in system settings, nothing is
 * scheduled; the preference is left intact and Settings shows the guidance when the
 * patient next interacts.
 */
export async function reassertReminder(plugin: ReminderPlugin = LocalNotifications): Promise<void> {
  if (!isNativePlatform()) {
    return;
  }
  const state = getReminderState();
  if (!state.enabled) {
    return;
  }
  const permission = await plugin.checkPermissions();
  if (permission.display !== 'granted') {
    return;
  }
  await plugin.schedule({
    notifications: [
      {
        id: REMINDER_NOTIFICATION_ID,
        title: REMINDER_TITLE,
        body: REMINDER_BODY,
        schedule: { on: { hour: state.hour, minute: state.minute }, allowWhileIdle: true },
      },
    ],
  });
}
