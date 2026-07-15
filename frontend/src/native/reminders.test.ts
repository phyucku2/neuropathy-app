/**
 * The daily check-in reminder seam (ADR-0029): permission → schedule → persist on
 * enable; cancel + persist on disable; a denied permission is a RESULT, never a
 * throw; web is a no-op. The plugin is injected (ADR-0024 seam lesson), so the
 * exact Cap-6 schedule shape is pinned here off-device.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../auth/platform', () => ({ isNativePlatform: vi.fn(() => false) }));

import { isNativePlatform } from '../auth/platform';
import {
  DEFAULT_REMINDER_HOUR,
  DEFAULT_REMINDER_MINUTE,
  disableReminder,
  disableReminderSilently,
  enableReminder,
  getReminderState,
  isReminderPermissionGranted,
  reassertReminder,
  REMINDER_BODY,
  REMINDER_NOTIFICATION_ID,
  REMINDER_PREF_KEY,
  REMINDER_TITLE,
} from './reminders';
import type { ReminderPlugin } from './reminders';

const nativeMock = vi.mocked(isNativePlatform);

function fakePlugin(display: 'granted' | 'denied' = 'granted') {
  return {
    checkPermissions: vi.fn(async () => ({ display })),
    requestPermissions: vi.fn(async () => ({ display })),
    schedule: vi.fn(async () => ({ notifications: [{ id: REMINDER_NOTIFICATION_ID }] })),
    cancel: vi.fn(async () => undefined),
  } satisfies ReminderPlugin & Record<string, ReturnType<typeof vi.fn>>;
}

/**
 * The exact Cap-6 payload `LocalNotifications.schedule` must receive
 * (@capacitor/local-notifications@6.1.3 definitions.d.ts — pinned the Style.Dark
 * way): `Schedule.on {hour, minute}` is the cron-like REPEATING form (Android
 * computes the next wall-clock match and re-registers after each fire — that IS
 * the daily repeat; `repeats` belongs to the one-shot `at` form, not `on`).
 * `allowWhileIdle` is best-effort only — delivery is approximate on modern Android
 * (see reminders.ts / ADR-0029 for the honest limits).
 */
function expectedSchedule(hour: number, minute: number) {
  return {
    notifications: [
      {
        id: REMINDER_NOTIFICATION_ID,
        title: REMINDER_TITLE,
        body: REMINDER_BODY,
        schedule: { on: { hour, minute }, allowWhileIdle: true },
      },
    ],
  };
}

beforeEach(() => {
  nativeMock.mockReset();
  nativeMock.mockReturnValue(true);
  localStorage.clear();
});

describe('notification content (PHI-free by construction)', () => {
  it('pins the fixed, PHI-free title and body — never any health data', () => {
    expect(REMINDER_TITLE).toBe('Daily check-in');
    expect(REMINDER_BODY).toBe('How are you feeling today? 30 seconds is all it takes.');
  });
});

describe('getReminderState', () => {
  it('defaults to disabled at 09:00 when nothing is stored', () => {
    expect(getReminderState()).toEqual({
      enabled: false,
      hour: DEFAULT_REMINDER_HOUR,
      minute: DEFAULT_REMINDER_MINUTE,
    });
    expect(DEFAULT_REMINDER_HOUR).toBe(9);
    expect(DEFAULT_REMINDER_MINUTE).toBe(0);
  });

  it('reads a stored preference back', () => {
    localStorage.setItem(
      REMINDER_PREF_KEY,
      JSON.stringify({ enabled: true, hour: 20, minute: 15 }),
    );
    expect(getReminderState()).toEqual({ enabled: true, hour: 20, minute: 15 });
  });

  it.each([
    ['corrupt JSON', 'not json'],
    ['wrong shape', JSON.stringify({ enabled: 'yes', hour: 9, minute: 0 })],
    ['out-of-range hour', JSON.stringify({ enabled: true, hour: 24, minute: 0 })],
    ['fractional minute', JSON.stringify({ enabled: true, hour: 9, minute: 0.5 })],
  ])('treats a %s entry as the default (never a crash or bogus time)', (_label, raw) => {
    localStorage.setItem(REMINDER_PREF_KEY, raw);
    expect(getReminderState()).toEqual({ enabled: false, hour: 9, minute: 0 });
  });
});

describe('enableReminder', () => {
  it('happy path: requests permission, schedules the daily repeating notification, persists', async () => {
    const plugin = fakePlugin('granted');
    await expect(enableReminder(8, 30, plugin)).resolves.toBe('scheduled');
    expect(plugin.requestPermissions).toHaveBeenCalledTimes(1);
    expect(plugin.schedule).toHaveBeenCalledTimes(1);
    expect(plugin.schedule).toHaveBeenCalledWith(expectedSchedule(8, 30));
    expect(getReminderState()).toEqual({ enabled: true, hour: 8, minute: 30 });
  });

  it('permission denied: returns the result (no throw), schedules nothing, persists nothing', async () => {
    const plugin = fakePlugin('denied');
    await expect(enableReminder(9, 0, plugin)).resolves.toBe('permission-denied');
    expect(plugin.schedule).not.toHaveBeenCalled();
    expect(getReminderState().enabled).toBe(false);
    expect(localStorage.getItem(REMINDER_PREF_KEY)).toBeNull();
  });

  it('web: no-op — no permission prompt, no schedule, nothing persisted', async () => {
    nativeMock.mockReturnValue(false);
    const plugin = fakePlugin('granted');
    await expect(enableReminder(9, 0, plugin)).resolves.toBe('unavailable');
    expect(plugin.requestPermissions).not.toHaveBeenCalled();
    expect(plugin.schedule).not.toHaveBeenCalled();
    expect(localStorage.getItem(REMINDER_PREF_KEY)).toBeNull();
  });

  it('a schedule failure does not persist an enabled preference the alarm does not back', async () => {
    const plugin = fakePlugin('granted');
    plugin.schedule.mockRejectedValueOnce(new Error('bridge fault'));
    await expect(enableReminder(9, 0, plugin)).rejects.toThrow('bridge fault');
    expect(localStorage.getItem(REMINDER_PREF_KEY)).toBeNull();
  });

  it.each([
    [24, 0],
    [-1, 0],
    [9, 60],
    [9.5, 0],
  ])(
    'rejects an out-of-range time %s:%s (programmer error, not a user path)',
    async (hour, minute) => {
      const plugin = fakePlugin('granted');
      await expect(enableReminder(hour, minute, plugin)).rejects.toThrow(RangeError);
      expect(plugin.requestPermissions).not.toHaveBeenCalled();
    },
  );
});

describe('disableReminder', () => {
  it('cancels the fixed notification id and persists off, KEEPING the chosen time', async () => {
    localStorage.setItem(
      REMINDER_PREF_KEY,
      JSON.stringify({ enabled: true, hour: 20, minute: 15 }),
    );
    const plugin = fakePlugin();
    await disableReminder(plugin);
    expect(plugin.cancel).toHaveBeenCalledWith({
      notifications: [{ id: REMINDER_NOTIFICATION_ID }],
    });
    expect(getReminderState()).toEqual({ enabled: false, hour: 20, minute: 15 });
  });

  it('web: persists off without touching the plugin', async () => {
    nativeMock.mockReturnValue(false);
    const plugin = fakePlugin();
    await disableReminder(plugin);
    expect(plugin.cancel).not.toHaveBeenCalled();
    expect(getReminderState().enabled).toBe(false);
  });
});

describe('disableReminderSilently (account-deletion cleanup — ADR-0027/0029)', () => {
  it('cancels the fixed notification id and REMOVES the stored preference entirely', async () => {
    localStorage.setItem(
      REMINDER_PREF_KEY,
      JSON.stringify({ enabled: true, hour: 20, minute: 15 }),
    );
    const plugin = fakePlugin();
    await disableReminderSilently(plugin);
    expect(plugin.cancel).toHaveBeenCalledWith({
      notifications: [{ id: REMINDER_NOTIFICATION_ID }],
    });
    // Unlike disableReminder (which keeps the time for re-enable), nothing survives:
    // the next signup on this device must not inherit a dead account's preference.
    expect(localStorage.getItem(REMINDER_PREF_KEY)).toBeNull();
  });

  it('never throws: a cancel fault is swallowed and the preference is still cleared', async () => {
    localStorage.setItem(REMINDER_PREF_KEY, JSON.stringify({ enabled: true, hour: 9, minute: 0 }));
    const plugin = fakePlugin();
    plugin.cancel.mockRejectedValueOnce(new Error('bridge fault'));
    await expect(disableReminderSilently(plugin)).resolves.toBeUndefined();
    expect(localStorage.getItem(REMINDER_PREF_KEY)).toBeNull();
  });

  it('web: clears the preference without touching the plugin', async () => {
    nativeMock.mockReturnValue(false);
    localStorage.setItem(REMINDER_PREF_KEY, JSON.stringify({ enabled: true, hour: 9, minute: 0 }));
    const plugin = fakePlugin();
    await disableReminderSilently(plugin);
    expect(plugin.cancel).not.toHaveBeenCalled();
    expect(localStorage.getItem(REMINDER_PREF_KEY)).toBeNull();
  });
});

describe('isReminderPermissionGranted', () => {
  it('reports the checkPermissions result — checks, never requests (no dialog ever)', async () => {
    const granted = fakePlugin('granted');
    await expect(isReminderPermissionGranted(granted)).resolves.toBe(true);
    expect(granted.checkPermissions).toHaveBeenCalledTimes(1);
    expect(granted.requestPermissions).not.toHaveBeenCalled();

    const denied = fakePlugin('denied');
    await expect(isReminderPermissionGranted(denied)).resolves.toBe(false);
    expect(denied.requestPermissions).not.toHaveBeenCalled();
  });

  it('web: true (nothing to grant, no guidance to show) without touching the plugin', async () => {
    nativeMock.mockReturnValue(false);
    const plugin = fakePlugin('denied');
    await expect(isReminderPermissionGranted(plugin)).resolves.toBe(true);
    expect(plugin.checkPermissions).not.toHaveBeenCalled();
  });
});

describe('reassertReminder (restore after reboot/app-update — ADR-0029)', () => {
  it('re-schedules an enabled reminder at its stored time when permission is granted', async () => {
    localStorage.setItem(REMINDER_PREF_KEY, JSON.stringify({ enabled: true, hour: 7, minute: 45 }));
    const plugin = fakePlugin('granted');
    await reassertReminder(plugin);
    expect(plugin.schedule).toHaveBeenCalledWith(expectedSchedule(7, 45));
  });

  it('never pops a permission dialog at launch: checks, does not request', async () => {
    localStorage.setItem(REMINDER_PREF_KEY, JSON.stringify({ enabled: true, hour: 7, minute: 45 }));
    const plugin = fakePlugin('granted');
    await reassertReminder(plugin);
    expect(plugin.checkPermissions).toHaveBeenCalledTimes(1);
    expect(plugin.requestPermissions).not.toHaveBeenCalled();
  });

  it('does nothing when the reminder is off', async () => {
    const plugin = fakePlugin('granted');
    await reassertReminder(plugin);
    expect(plugin.checkPermissions).not.toHaveBeenCalled();
    expect(plugin.schedule).not.toHaveBeenCalled();
  });

  it('does nothing when permission was revoked in system settings (preference kept for the Settings hint)', async () => {
    localStorage.setItem(REMINDER_PREF_KEY, JSON.stringify({ enabled: true, hour: 7, minute: 45 }));
    const plugin = fakePlugin('denied');
    await reassertReminder(plugin);
    expect(plugin.schedule).not.toHaveBeenCalled();
    expect(getReminderState().enabled).toBe(true);
  });

  it('web: no-op', async () => {
    nativeMock.mockReturnValue(false);
    localStorage.setItem(REMINDER_PREF_KEY, JSON.stringify({ enabled: true, hour: 7, minute: 45 }));
    const plugin = fakePlugin('granted');
    await reassertReminder(plugin);
    expect(plugin.checkPermissions).not.toHaveBeenCalled();
    expect(plugin.schedule).not.toHaveBeenCalled();
  });
});
