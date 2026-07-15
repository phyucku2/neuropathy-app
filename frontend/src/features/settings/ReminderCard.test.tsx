/**
 * The "Daily reminder" card (ADR-0029): native-only toggle + time input over the
 * reminders seam; web renders the honest fallback with a disabled toggle. The seam
 * and the platform gate are local modules, mocked reliably (ADR-0024 seam lesson) —
 * the seam's own behavior is locked in src/native/reminders.test.ts.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../auth/platform', () => ({ isNativePlatform: vi.fn(() => false) }));
vi.mock('../../native/reminders', () => ({
  getReminderState: vi.fn(() => ({ enabled: false, hour: 9, minute: 0 })),
  enableReminder: vi.fn(async () => 'scheduled' as const),
  disableReminder: vi.fn(async () => undefined),
}));

import { isNativePlatform } from '../../auth/platform';
import { disableReminder, enableReminder, getReminderState } from '../../native/reminders';
import { ReminderCard } from './ReminderCard';

const nativeMock = vi.mocked(isNativePlatform);
const getStateMock = vi.mocked(getReminderState);
const enableMock = vi.mocked(enableReminder);
const disableMock = vi.mocked(disableReminder);

beforeEach(() => {
  nativeMock.mockReset().mockReturnValue(true);
  getStateMock.mockReset().mockReturnValue({ enabled: false, hour: 9, minute: 0 });
  enableMock.mockReset().mockResolvedValue('scheduled');
  disableMock.mockReset().mockResolvedValue(undefined);
});

describe('ReminderCard — web fallback', () => {
  it('renders the toggle disabled with the mobile-app note and no time input', () => {
    nativeMock.mockReturnValue(false);
    render(<ReminderCard />);
    expect(screen.getByText('Reminders are available in the mobile app')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Daily check-in reminder' })).toBeDisabled();
    expect(screen.queryByLabelText('Reminder time')).not.toBeInTheDocument();
  });
});

describe('ReminderCard — native', () => {
  it('enables at the default 09:00 and reflects the on state', async () => {
    const user = userEvent.setup();
    render(<ReminderCard />);
    const toggle = screen.getByRole('switch', { name: 'Daily check-in reminder' });
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('Off')).toBeInTheDocument();
    await user.click(toggle);
    await waitFor(() => {
      expect(toggle).toHaveAttribute('aria-checked', 'true');
    });
    expect(enableMock).toHaveBeenCalledWith(9, 0);
    expect(screen.getByText('On · every day at 09:00')).toBeInTheDocument();
  });

  it('restores a stored enabled preference (toggle on, stored time in the input)', () => {
    getStateMock.mockReturnValue({ enabled: true, hour: 20, minute: 15 });
    render(<ReminderCard />);
    expect(screen.getByRole('switch', { name: 'Daily check-in reminder' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByLabelText('Reminder time')).toHaveValue('20:15');
  });

  it('disables the toggle while the enable is pending', async () => {
    let resolve!: (value: 'scheduled') => void;
    enableMock.mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const user = userEvent.setup();
    render(<ReminderCard />);
    const toggle = screen.getByRole('switch', { name: 'Daily check-in reminder' });
    await user.click(toggle);
    expect(toggle).toBeDisabled();
    expect(screen.getByLabelText('Reminder time')).toBeDisabled();
    resolve('scheduled');
    await waitFor(() => {
      expect(toggle).not.toBeDisabled();
    });
  });

  it('renders the system-settings guidance (role=status) on permission-denied — not an error', async () => {
    enableMock.mockResolvedValue('permission-denied');
    const user = userEvent.setup();
    render(<ReminderCard />);
    await user.click(screen.getByRole('switch', { name: 'Daily check-in reminder' }));
    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent(/Allow notifications in your phone’s system settings/);
    // The toggle stays off — nothing was scheduled.
    expect(screen.getByRole('switch', { name: 'Daily check-in reminder' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });

  it('changing the time while enabled reschedules at the new time', async () => {
    getStateMock.mockReturnValue({ enabled: true, hour: 9, minute: 0 });
    render(<ReminderCard />);
    const input = screen.getByLabelText('Reminder time');
    // A native time picker commits a complete value in ONE change event —
    // fireEvent.change models that (userEvent keystrokes don't fit <input type=time>).
    fireEvent.change(input, { target: { value: '07:45' } });
    await waitFor(() => {
      expect(enableMock).toHaveBeenCalledWith(7, 45);
    });
    expect(input).toHaveValue('07:45');
  });

  it('changing the time while disabled only updates the input — nothing is scheduled', () => {
    render(<ReminderCard />);
    const input = screen.getByLabelText('Reminder time');
    fireEvent.change(input, { target: { value: '07:45' } });
    expect(input).toHaveValue('07:45');
    expect(enableMock).not.toHaveBeenCalled();
  });

  it('toggling off cancels via the seam and shows Off', async () => {
    getStateMock.mockReturnValue({ enabled: true, hour: 9, minute: 0 });
    const user = userEvent.setup();
    render(<ReminderCard />);
    const toggle = screen.getByRole('switch', { name: 'Daily check-in reminder' });
    await user.click(toggle);
    await waitFor(() => {
      expect(toggle).toHaveAttribute('aria-checked', 'false');
    });
    expect(disableMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Off')).toBeInTheDocument();
  });

  it('a seam fault on enable surfaces the retry hint and leaves the toggle off', async () => {
    enableMock.mockRejectedValue(new Error('bridge fault'));
    const user = userEvent.setup();
    render(<ReminderCard />);
    await user.click(screen.getByRole('switch', { name: 'Daily check-in reminder' }));
    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('The reminder couldn’t be updated. Please try again.');
    expect(screen.getByRole('switch', { name: 'Daily check-in reminder' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });

  it('a seam fault on disable surfaces the retry hint and keeps the toggle on', async () => {
    getStateMock.mockReturnValue({ enabled: true, hour: 9, minute: 0 });
    disableMock.mockRejectedValue(new Error('bridge fault'));
    const user = userEvent.setup();
    render(<ReminderCard />);
    await user.click(screen.getByRole('switch', { name: 'Daily check-in reminder' }));
    await screen.findByRole('status');
    expect(screen.getByRole('switch', { name: 'Daily check-in reminder' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });
});
