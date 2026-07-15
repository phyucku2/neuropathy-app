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

import { useState } from 'react';
import { isNativePlatform } from '../../auth/platform';
import { disableReminder, enableReminder, getReminderState } from '../../native/reminders';

const PERMISSION_HINT =
  'Notifications are turned off for this app. Allow notifications in your phone’s system settings, then try again.';
const GENERIC_HINT = 'The reminder couldn’t be updated. Please try again.';

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

  const schedule = async (value: string) => {
    const { hour, minute } = parseTimeValue(value);
    setPending(true);
    setHint(null);
    try {
      const result = await enableReminder(hour, minute);
      if (result === 'scheduled') {
        setEnabled(true);
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
                setTime(value);
                // An enabled reminder follows the new time immediately (the fixed
                // notification id makes re-scheduling replace the pending alarm).
                if (enabled && value !== '') {
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
