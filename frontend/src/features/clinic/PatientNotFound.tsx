/**
 * The neutral not-found screen for any 404 under /clinic/patients/{id}/*.
 *
 * The backend deliberately answers 404 — never 403 — for cross-clinic,
 * non-consented, revoked, AND nonexistent patients (ADR-0012), so this screen
 * must stay just as neutral: it never says "no access", because that would
 * re-introduce the existence distinction the API is designed to hide.
 */

import { Link } from 'react-router-dom';

export function PatientNotFound() {
  return (
    <div>
      <h1>Patient not found</h1>
      <div className="empty-state">
        <p style={{ marginTop: 0 }}>There is no patient record at this address.</p>
        <p style={{ marginBottom: 0 }}>
          <Link className="link" to="/clinic">
            Back to your panel
          </Link>
        </p>
      </div>
    </div>
  );
}
