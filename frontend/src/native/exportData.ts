/**
 * "Download my data" delivery seam (ADR-0031), platform-selected like every other
 * native seam (ADR-0024/0025): pure helpers plus injectable plugin accessors, so every
 * decision is unit-testable off-device and the web/E2E path never touches a plugin.
 *
 * - **Web**: trigger a browser file download of the export JSON, plus a flattened CSV
 *   of the observations table (a spreadsheet-friendly companion). Blob + object URL.
 * - **Native**: local notifications-style — write the JSON to the app's cache
 *   directory (@capacitor/filesystem) and open the OS Share sheet (@capacitor/share)
 *   so the patient can save it to Files, email it, etc. There is no browser "download"
 *   on a phone; sharing a written file is the platform-native equivalent.
 *
 * The export payload itself is token/secret free by construction (backend
 * schemas/export.py); this module only formats and delivers it.
 */

import { Directory, Encoding, Filesystem } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
import type { ExportObservation, ExportOut } from '../api/types';
import { isNativePlatform } from '../auth/platform';

/** Base filename stem for a given day, e.g. `neuropathy-export-2026-07-15`. */
export function exportFilenameStem(now: Date): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `neuropathy-export-${year}-${month}-${day}`;
}

/** The observation columns flattened to CSV, in a stable order. Objects (quality,
 *  payload) are intentionally excluded — CSV is the spreadsheet-friendly scalar view;
 *  the full nested detail lives in the JSON. */
const CSV_COLUMNS: readonly (keyof ExportObservation)[] = [
  'effective_at',
  'recorded_at',
  'source',
  'origin',
  'code',
  'code_system',
  'value_num',
  'value_text',
  'unit',
  'unit_system',
  'status',
];

/** Escape one CSV cell (RFC 4180): quote when it contains a comma, quote, or newline,
 *  doubling any embedded quotes. null/undefined become an empty cell. */
function csvCell(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  const text = String(value);
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

/**
 * Flatten the observations table to a CSV string (pure — unit-locked). Always emits
 * the header row, so an empty export yields a valid, header-only CSV rather than an
 * empty file. Rows are CRLF-terminated per RFC 4180.
 */
export function observationsToCsv(observations: ExportObservation[]): string {
  const header = CSV_COLUMNS.join(',');
  const rows = observations.map((observation) =>
    CSV_COLUMNS.map((column) => csvCell(observation[column])).join(','),
  );
  return [header, ...rows].join('\r\n');
}

/**
 * Trigger a browser download of a Blob under a filename (web only). Uses an object URL
 * + a synthetic anchor click, revoking the URL afterwards. jsdom has no real
 * createObjectURL, so unit tests stub it; the real path is proven in the E2E.
 */
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** The slice of @capacitor/filesystem the seam uses, injectable for unit tests. */
export interface FilesystemLike {
  writeFile(options: {
    path: string;
    data: string;
    directory: Directory;
    encoding: Encoding;
  }): Promise<{ uri: string }>;
  deleteFile(options: { path: string; directory: Directory }): Promise<void>;
}

/** The slice of @capacitor/share the seam uses, injectable for unit tests. */
export interface ShareLike {
  share(options: { title?: string; text?: string; url?: string }): Promise<unknown>;
}

/**
 * Was a rejected `share.share(...)` the user simply dismissing the OS share sheet?
 *
 * @capacitor/share v6 REJECTS on cancellation (iOS surfaces "Share canceled"), which
 * is NOT an error — the file was already written and the user just changed their mind.
 * The exact rejection shape varies by platform, so match defensively on a `code` field
 * or a message substring rather than an exact string. (This native branch is
 * unverifiable locally — no Android SDK, the same boundary ADR-0031/ADR-0023 declare;
 * on-device proof is `npx cap run android`.)
 */
function isShareCancellation(cause: unknown): boolean {
  const code =
    typeof cause === 'object' && cause !== null ? (cause as { code?: unknown }).code : undefined;
  if (typeof code === 'string' && /cancel/i.test(code)) {
    return true;
  }
  const message = cause instanceof Error ? cause.message : String(cause ?? '');
  return /cancel/i.test(message);
}

/**
 * Best-effort removal of the cache copy after the Share flow (data-at-rest hygiene:
 * the dump is app-private, but there is no reason to leave the full PHI file lingering
 * once the share sheet closes or is cancelled). A cleanup failure must NEVER surface as
 * a user-facing error on an otherwise-successful export, so it is swallowed.
 */
async function deleteExportFile(filesystem: FilesystemLike, path: string): Promise<void> {
  try {
    await filesystem.deleteFile({ path, directory: Directory.Cache });
  } catch {
    // Swallow — the export already succeeded (or was cancelled); a failed cache
    // delete is not something to alarm the patient about.
  }
}

export interface SaveExportDeps {
  isNative: () => boolean;
  download: (blob: Blob, filename: string) => void;
  filesystem: FilesystemLike;
  share: ShareLike;
  now: () => Date;
}

const DEFAULT_DEPS: SaveExportDeps = {
  isNative: isNativePlatform,
  download: triggerDownload,
  filesystem: Filesystem,
  share: Share,
  now: () => new Date(),
};

/**
 * Deliver an export to the patient, platform-appropriately.
 *
 * Native: write the JSON to the cache directory and open the Share sheet. Web: download
 * the JSON file and a flattened observations CSV. The native branch is gated behind
 * `isNativePlatform()` (injected) so the web build and E2E never call a plugin.
 */
export async function saveExport(
  data: ExportOut,
  deps: Partial<SaveExportDeps> = {},
): Promise<void> {
  const { isNative, download, filesystem, share, now } = { ...DEFAULT_DEPS, ...deps };
  const stem = exportFilenameStem(now());
  const json = JSON.stringify(data, null, 2);

  if (isNative()) {
    const filename = `${stem}.json`;
    const written = await filesystem.writeFile({
      path: filename,
      data: json,
      directory: Directory.Cache,
      encoding: Encoding.UTF8,
    });
    try {
      await share.share({
        title: 'Your health data export',
        text: 'Your exported health data',
        url: written.uri,
      });
    } catch (cause) {
      // A cancelled share sheet is a NON-error (the export succeeded; the user just
      // dismissed it) — resolve normally. A genuine share/bridge failure still throws
      // and the card renders it in its role=alert.
      if (!isShareCancellation(cause)) {
        throw cause;
      }
    } finally {
      // Runs on success AND cancellation AND a real failure: the cache copy never
      // outlives the share flow (best-effort; never throws — see deleteExportFile).
      await deleteExportFile(filesystem, filename);
    }
    return;
  }

  // Web: two downloads (JSON + spreadsheet-friendly CSV) fired back-to-back in the
  // SAME user gesture — browsers permit multiple downloads per click, so this must NOT
  // be split across awaits/ticks or a later download would be blocked as not
  // user-initiated. Kept as two files by design (no zip dependency, ADR-0031).
  download(new Blob([json], { type: 'application/json' }), `${stem}.json`);
  download(new Blob([observationsToCsv(data.observations)], { type: 'text/csv' }), `${stem}.csv`);
}
