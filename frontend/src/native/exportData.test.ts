/**
 * The "Download my data" delivery seam (ADR-0031): the pure CSV flattener + filename
 * stem, the web blob-download path, and the native write-file + Share path. The seam's
 * plugins/platform are injected (ADR-0024 seam lesson) so both branches are unit-locked
 * off-device; the real DOM download is proven end-to-end in Playwright.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { EXPORT, EXPORT_OBSERVATIONS } from '../test/fixtures';
import type { ExportOut } from '../api/types';
import {
  exportFilenameStem,
  observationsToCsv,
  saveExport,
  triggerDownload,
  type FilesystemLike,
  type ShareLike,
} from './exportData';

describe('observationsToCsv (pure)', () => {
  it('emits a header even for an empty export (a valid, header-only CSV)', () => {
    const csv = observationsToCsv([]);
    expect(csv).toBe(
      'effective_at,recorded_at,source,origin,code,code_system,value_num,value_text,unit,unit_system,status',
    );
  });

  it('flattens the scalar columns and RFC-4180-escapes commas and quotes', () => {
    const csv = observationsToCsv(EXPORT_OBSERVATIONS);
    const lines = csv.split('\r\n');
    expect(lines).toHaveLength(3); // header + 2 rows
    // Row 1: a plain lab value.
    expect(lines[1]).toContain('4548-4');
    expect(lines[1]).toContain('7.2');
    // Row 2: value_text has a comma AND embedded quotes -> wrapped, quotes doubled;
    // the unit has a comma -> wrapped. Objects (quality/payload) are NOT columns.
    expect(lines[2]).toContain('"steady, ""good"" day"');
    expect(lines[2]).toContain('"{score}, per day"');
    expect(csv).not.toContain('human_confirmed');
  });

  it('renders null cells as empty, never the string "null"', () => {
    const base = EXPORT_OBSERVATIONS[0];
    if (base === undefined) throw new Error('fixture missing');
    const csv = observationsToCsv([
      { ...base, value_num: null, value_text: null, code_system: null },
    ]);
    expect(csv).not.toContain('null');
  });
});

describe('exportFilenameStem', () => {
  it('formats the local date as neuropathy-export-YYYY-MM-DD', () => {
    expect(exportFilenameStem(new Date(2026, 6, 5))).toBe('neuropathy-export-2026-07-05');
  });
});

describe('triggerDownload (web)', () => {
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;

  afterEach(() => {
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  });

  it('creates an object URL, clicks a download anchor, and revokes the URL', () => {
    const createObjectURL = vi.fn(() => 'blob:mock-url');
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL as unknown as typeof URL.createObjectURL;
    URL.revokeObjectURL = revokeObjectURL as unknown as typeof URL.revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    const blob = new Blob(['{}'], { type: 'application/json' });
    triggerDownload(blob, 'neuropathy-export-2026-07-15.json');

    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
    // The anchor was cleaned up after the click.
    expect(document.querySelector('a[download]')).toBeNull();
  });
});

describe('saveExport — platform branch', () => {
  const fixedNow = () => new Date(2026, 6, 15);

  it('web: downloads the JSON and a CSV of the observations, never touching a plugin', async () => {
    const download = vi.fn();
    const filesystem: FilesystemLike = { writeFile: vi.fn(), deleteFile: vi.fn() };
    const share: ShareLike = { share: vi.fn() };

    await saveExport(EXPORT, {
      isNative: () => false,
      download,
      filesystem,
      share,
      now: fixedNow,
    });

    expect(download).toHaveBeenCalledTimes(2);
    const [jsonBlob, jsonName] = download.mock.calls[0] as [Blob, string];
    const [csvBlob, csvName] = download.mock.calls[1] as [Blob, string];
    expect(jsonName).toBe('neuropathy-export-2026-07-15.json');
    expect(jsonBlob.type).toBe('application/json');
    expect(csvName).toBe('neuropathy-export-2026-07-15.csv');
    expect(csvBlob.type).toBe('text/csv');
    expect(filesystem.writeFile).not.toHaveBeenCalled();
    expect(share.share).not.toHaveBeenCalled();
  });

  it('web: falls back to the current date when now is not injected (covers the default dep)', async () => {
    // No `now` override -> DEFAULT_DEPS.now (`() => new Date()`) runs, so its lambda is
    // exercised. We only assert the shape of today's stem, never a fixed value.
    const download = vi.fn();
    await saveExport(EXPORT, {
      isNative: () => false,
      download,
      filesystem: { writeFile: vi.fn(), deleteFile: vi.fn() },
      share: { share: vi.fn() },
    });
    const [, jsonName] = download.mock.calls[0] as [Blob, string];
    expect(jsonName).toMatch(/^neuropathy-export-\d{4}-\d{2}-\d{2}\.json$/);
  });

  it('native: writes the JSON to the cache dir, opens the Share sheet, then deletes the file', async () => {
    const download = vi.fn();
    const writeFile = vi.fn(async () => ({ uri: 'file:///cache/neuropathy-export.json' }));
    const deleteFile = vi.fn(async () => undefined);
    const share = vi.fn(async () => undefined);

    await saveExport(EXPORT, {
      isNative: () => true,
      download,
      filesystem: { writeFile, deleteFile },
      share: { share },
      now: fixedNow,
    });

    // Written to the cache dir under the day's filename, with the pretty-printed JSON.
    expect(writeFile).toHaveBeenCalledTimes(1);
    expect(writeFile).toHaveBeenCalledWith(
      expect.objectContaining({
        path: 'neuropathy-export-2026-07-15.json',
        data: expect.stringContaining('"schema_version": "1.1"'),
      }),
    );
    expect(share).toHaveBeenCalledWith(
      expect.objectContaining({ url: 'file:///cache/neuropathy-export.json' }),
    );
    // Data-at-rest hygiene: the cache copy is deleted after the share flow.
    expect(deleteFile).toHaveBeenCalledTimes(1);
    expect(deleteFile).toHaveBeenCalledWith(
      expect.objectContaining({ path: 'neuropathy-export-2026-07-15.json' }),
    );
    expect(download).not.toHaveBeenCalled();
  });

  it('native: a cancelled Share sheet is a NON-error and still cleans up the cache file', async () => {
    const deleteFile = vi.fn(async () => undefined);
    // iOS-style cancellation message (Capacitor Share v6 rejects on dismissal).
    const share = vi.fn(async () => {
      throw new Error('Share canceled');
    });

    await expect(
      saveExport(EXPORT, {
        isNative: () => true,
        download: vi.fn(),
        filesystem: { writeFile: vi.fn(async () => ({ uri: 'file:///cache/x.json' })), deleteFile },
        share: { share },
        now: fixedNow,
      }),
    ).resolves.toBeUndefined();
    expect(deleteFile).toHaveBeenCalledTimes(1);
  });

  it('native: a cancellation signalled by a `code` field is also treated as success', async () => {
    const deleteFile = vi.fn(async () => undefined);
    const share = vi.fn(async () => {
      throw { code: 'CANCELLED', message: 'user dismissed' };
    });

    await expect(
      saveExport(EXPORT, {
        isNative: () => true,
        download: vi.fn(),
        filesystem: { writeFile: vi.fn(async () => ({ uri: 'file:///cache/x.json' })), deleteFile },
        share: { share },
        now: fixedNow,
      }),
    ).resolves.toBeUndefined();
    expect(deleteFile).toHaveBeenCalledTimes(1);
  });

  it('native: a genuine Share failure still propagates to the caller (the card renders it)', async () => {
    const deleteFile = vi.fn(async () => undefined);
    const share = vi.fn(async () => {
      throw new Error('share bridge exploded');
    });

    await expect(
      saveExport(EXPORT, {
        isNative: () => true,
        download: vi.fn(),
        filesystem: { writeFile: vi.fn(async () => ({ uri: 'file:///cache/x.json' })), deleteFile },
        share: { share },
        now: fixedNow,
      }),
    ).rejects.toThrow('share bridge exploded');
    // Cleanup still ran (finally), even though the failure propagated.
    expect(deleteFile).toHaveBeenCalledTimes(1);
  });

  it('native: a cache-cleanup failure never surfaces as a user-facing error', async () => {
    const share = vi.fn(async () => undefined);
    const deleteFile = vi.fn(async () => {
      throw new Error('unlink failed');
    });

    await expect(
      saveExport(EXPORT, {
        isNative: () => true,
        download: vi.fn(),
        filesystem: { writeFile: vi.fn(async () => ({ uri: 'file:///cache/x.json' })), deleteFile },
        share: { share },
        now: fixedNow,
      }),
    ).resolves.toBeUndefined();
  });

  it('propagates an API/plugin write failure to the caller (the card renders it)', async () => {
    const failing: ExportOut = EXPORT;
    await expect(
      saveExport(failing, {
        isNative: () => true,
        download: vi.fn(),
        filesystem: {
          writeFile: vi.fn(async () => {
            throw new Error('disk full');
          }),
          deleteFile: vi.fn(),
        },
        share: { share: vi.fn() },
        now: fixedNow,
      }),
    ).rejects.toThrow('disk full');
  });
});
