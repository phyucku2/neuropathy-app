/**
 * "Visit summary" entry point on the Sources surface (ADR-0045) — sits with the other
 * take-your-data-out affordances (Your records, Download my data). A card/link, NOT a sixth
 * bottom-nav tab: five tabs is the accessible max (ADR-0039), and the handout is a purposeful
 * print artifact reached when the patient is preparing for a visit, not a primary destination.
 */

import { Link } from 'react-router-dom';

export function VisitSummaryLinkCard() {
  return (
    <>
      <h2>Visit summary</h2>
      <div className="card">
        <div className="src">
          <span className="ic" style={{ background: 'var(--color-brand-blue)' }} aria-hidden="true">
            🖨
          </span>
          <div className="info">
            <b>Summary for your appointment</b>
            <small>
              A short, printable summary of your recorded data to bring to your next visit.
            </small>
          </div>
        </div>
        <Link className="btn-inline" to="/handout">
          Open visit summary
        </Link>
      </div>
    </>
  );
}
