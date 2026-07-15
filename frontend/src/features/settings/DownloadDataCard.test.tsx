/**
 * "Download my data" card (ADR-0031): the pending role=status, the success state, the
 * verbatim API-error alert, and delegation to the platform delivery seam. The seam
 * (saveExport) is mocked here so the card is tested in isolation; the seam's own
 * web-vs-native branch is locked in src/native/exportData.test.ts.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../native/exportData', () => ({ saveExport: vi.fn(async () => undefined) }));

import { saveExport } from '../../native/exportData';
import { EXPORT } from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { server } from '../../test/server';

const saveExportMock = vi.mocked(saveExport);

beforeEach(() => {
  saveExportMock.mockClear();
  saveExportMock.mockResolvedValue(undefined);
});

async function goToSettings() {
  const user = userEvent.setup();
  renderApp('/settings');
  // The card sits above the danger zone; wait for it to render.
  await screen.findByRole('button', { name: 'Download my data' });
  return user;
}

describe('SettingsPage — Download my data card', () => {
  it('sits above the danger zone (right-of-access before deletion)', async () => {
    await goToSettings();
    const download = screen.getByRole('button', { name: 'Download my data' });
    const del = screen.getByRole('button', { name: 'Delete my account' });
    // Document order: the download card precedes the danger zone.
    expect(download.compareDocumentPosition(del) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('fetches the export and hands it to the delivery seam, then shows success', async () => {
    const user = await goToSettings();
    await user.click(screen.getByRole('button', { name: 'Download my data' }));

    await waitFor(() => {
      expect(saveExportMock).toHaveBeenCalledTimes(1);
    });
    // The seam received the exact export the API returned (the real ExportOut shape).
    expect(saveExportMock).toHaveBeenCalledWith(EXPORT);
    expect(await screen.findByText('Your data is ready.')).toBeInTheDocument();
  });

  it('shows role=status "Preparing your data…" and disables the button while pending', async () => {
    server.use(
      http.get('/me/export', async () => {
        await delay(150);
        return HttpResponse.json(EXPORT);
      }),
    );
    const user = await goToSettings();
    await user.click(screen.getByRole('button', { name: 'Download my data' }));

    // Pending: the live-region status appears and the button is disabled.
    expect(await screen.findByText('Preparing your data…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download my data' })).toBeDisabled();

    await waitFor(() => {
      expect(screen.getByText('Your data is ready.')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Download my data' })).toBeEnabled();
  });

  it('surfaces a verbatim API error in a role=alert and never calls the seam', async () => {
    server.use(
      http.get('/me/export', () =>
        HttpResponse.json({ detail: 'Patient account required' }, { status: 403 }),
      ),
    );
    const user = await goToSettings();
    await user.click(screen.getByRole('button', { name: 'Download my data' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Patient account required'); // verbatim
    expect(saveExportMock).not.toHaveBeenCalled();
    // The button is re-enabled so the patient can retry.
    expect(screen.getByRole('button', { name: 'Download my data' })).toBeEnabled();
  });
});
