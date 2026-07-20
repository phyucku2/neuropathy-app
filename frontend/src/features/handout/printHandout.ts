/**
 * Print seam for the Visit-Ready Summary (ADR-0045), platform-selected like every other
 * native seam (ADR-0024/0025): the print function and platform check are injected, so both
 * branches are unit-testable off-device and jsdom (which has no real `window.print`) never
 * throws.
 *
 * - **Web**: call `window.print()`. The @media print stylesheet (src/styles/app.css) hides the
 *   app chrome and lays the summary out as a one-to-two-page sheet; the browser's own dialog
 *   drives the paper/PDF choice — no PDF dependency in the bundle (jsPDF/html2canvas banned,
 *   ADR-0045 bundle budget).
 * - **Native**: the Capacitor webview has no system print dialog. This is a no-op that never
 *   throws — the patient saves/shares the record via the existing export seam instead.
 */

import { isNativePlatform } from '../../auth/platform';

export interface PrintDeps {
  isNative: () => boolean;
  print: () => void;
}

const DEFAULT_DEPS: PrintDeps = {
  isNative: isNativePlatform,
  // Guarded call: jsdom leaves `window.print` undefined, and a native webview has no dialog —
  // the native branch below never reaches this, and unit tests inject their own spy.
  print: () => {
    window.print();
  },
};

/**
 * Open the browser print dialog for the current handout (web), or no-op on native. Injectable
 * for tests; never throws on native or in jsdom.
 */
export function printHandout(deps: Partial<PrintDeps> = {}): void {
  const { isNative, print } = { ...DEFAULT_DEPS, ...deps };
  if (isNative()) {
    // No system print dialog inside the Capacitor webview — the patient uses the OS
    // share/save flow (export seam) instead. Do nothing, but never throw.
    return;
  }
  print();
}
