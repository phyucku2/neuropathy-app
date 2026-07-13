/**
 * The non-diagnostic disclaimer (product requirement from the approved
 * mockup): no clinician screen may present a computed direction as a
 * diagnosis. Shown on the trajectory and cross-source trend-table views.
 */

export const NON_DIAGNOSTIC_TEXT = 'Trends support clinical judgment; they are not a diagnosis.';

export function NonDiagnosticNote() {
  return <p className="disclaimer">{NON_DIAGNOSTIC_TEXT}</p>;
}
