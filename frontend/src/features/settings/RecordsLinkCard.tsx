/**
 * "Your records" entry point on the Sources surface — the natural home, right beside
 * the EMR connection card (records ARE what an EMR connection brings in). A card/link,
 * NOT a sixth bottom-nav tab: five tabs is the accessible max (ADR-0039), and Records
 * is a read-only detail view reached from where the connection is managed, not a
 * primary destination.
 */

import { Link } from 'react-router-dom';

export function RecordsLinkCard() {
  return (
    <>
      <h2>Your records</h2>
      <div className="card">
        <div className="src">
          <span className="ic" style={{ background: 'var(--color-brand-blue)' }} aria-hidden="true">
            🗂
          </span>
          <div className="info">
            <b>Your health record</b>
            <small>
              A read-only copy of the labs and results we&apos;ve pulled from your record.
            </small>
          </div>
        </div>
        <Link className="btn-inline" to="/records">
          View your records
        </Link>
      </div>
    </>
  );
}
