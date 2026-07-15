/**
 * "Daily reminder" (ADR-0029) — a device-local daily nudge to do the ADL check-in.
 *
 * Native-only: local notifications exist only inside the Capacitor shell, so on web
 * the toggle renders disabled with an honest "available in the mobile app" note
 * (`isNativePlatform` gate). The preference (enabled + time) lives in localStorage
 * via the reminders seam — a per-device choice, never server state.
 *
 * A denied OS permission is a RESULT, not an error: the seam returns
 * 'permission-denied' and this card renders inline guidance (role="status")
 * pointing at the phone's system settings.
 */

import { useEffect, useState } from 'react';
import { isNativePlatform } from '../../auth/platform';
import {
  disableReminder,
  enableReminder,
  getReminderState,
  isReminderPermissionGranted,
} from '../../native/reminders';

const PERMISSION_HINT =
  'Notifications are turned off for this app. Allow notifications in your phone’s system settings, then try again.';
const GENERIC_HINT = 'The reminder couldn’t be updated. Please try again.';
const PICK_TIME_HINT = 'Pick a time first, then turn the reminder on.';

/** "hh:mm" (the <input type="time"> value) → {hour, minute}. */
function parseTimeValue(value: string): { hour: number; minute: number } {
  const [hour = NaN, minute = NaN] = value.split(':').map(Number);
  return { hour, minute };
}

function toTimeValue(hour: number, minute: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

export function ReminderCard() {
  const native = isNativePlatform();
  const [enabled, setEnabled] = useState(() => native && getReminderState().enabled);
  const [time, setTime] = useState(() => {
    const state = getReminderState();
    return toTimeValue(state.hour, state.minute);
  });
  const [pending, setPending] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  // A stored "enabled" preference is only honest while the OS permission is still
  // granted — it can be revoked in system settings at any time, after which nothing
  // will ever fire. Probe on mount (check only — never a prompt) and render the
  // system-settings guidance immediately instead of a clean "On" state.
  useEffect(() => {
    if (!native || !enabled) {
      return;
    }
    let cancelled = false;
    void isReminderPermissionGranted()
      .then((granted) => {
        if (!cancelled && !granted) {
          setHint(PERMISSION_HINT);
        }
      })
      .catch(() => {
        // Probe fault: no hint — the toggle itself still reports honestly on use.
      });
    return () => {
      cancelled = true;
    };
  }, [native, enabled]);

  const schedule = async (value: string) => {
    const { hour, minute } = parseTimeValue(value);
    setPending(true);
    setHint(null);
    try {
      const result = await enableReminder(hour, minute);
      if (result === 'scheduled') {
        setEnabled(true);
        // Commit the time only once the alarm actually moved: on any failure the
        // card keeps showing the time that is still scheduled, never a time that
        // will not fire.
        setTime(value);
      } else if (result === 'permission-denied') {
        setHint(PERMISSION_HINT);
      }
    } catch {
      // A plugin/bridge fault — the reminder state is unchanged; honest retry hint.
      setHint(GENERIC_HINT);
    } finally {
      setPending(false);
    }
  };

  const toggle = async () => {
    if (enabled) {
      setPending(true);
      setHint(null);
      try {
        await disableReminder();
        setEnabled(false);
      } catch {
        setHint(GENERIC_HINT);
      } finally {
        setPending(false);
      }
    } else if (time === '') {
      // Some pickers let the value be cleared; scheduling '' is a programmer-error
      // throw in the seam, so guide instead of a generic failure.
      setHint(PICK_TIME_HINT);
    } else {
      await schedule(time);
    }
  };

  return (
    <>
      <h2>Daily reminder</h2>
      <div className="card">
        <div className="src">
          <span
            className="ic"
            style={{ background: 'var(--color-action-green)' }}
            aria-hidden="true"
          >
            🔔
          </span>
          <div className="info">
            <b>Daily check-in reminder</b>
            <small>
              {!native
                ? 'Reminders are available in the mobile app'
                : enabled
                  ? `On · every day at ${time}`
                  : 'Off'}
            </small>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            aria-label="Daily check-in reminder"
            className="tg"
            disabled={!native || pending}
            onClick={() => {
              void toggle();
            }}
          />
        </div>
        {native && (
          <div className="field">
            <label htmlFor="reminder-time">Reminder time</label>
            <input
              id="reminder-time"
              type="time"
              value={time}
              disabled={pending}
              onChange={(event) => {
                const value = event.target.value;
                if (!enabled) {
                  // Disabled: just track the picker (an empty value is guarded at
                  // toggle-on with the pick-a-time hint).
                  setTime(value);
                  return;
                }
                // Enabled: an empty value is ignored outright — the old time is
                // what still fires, so it stays shown. A real value reschedules
                // (the fixed notification id replaces the pending alarm) and is
                // committed to state only on success (see schedule()).
                if (value !== '') {
                  void schedule(value);
                }
              }}
            />
          </div>
        )}
        {hint !== null && (
          <p className="muted" role="status" style={{ margin: 0 }}>
            {hint}
          </p>
        )}
      </div>
      <p className="muted centered">
        A gentle nudge on this device only — it never includes any of your health information.
      </p>
    </>
  );
}
