/**
 * Panel — the clinician's home (mockups/clinician-app.html): the list of
 * patients with an active, consented connection to this clinic, plus the
 * invite-a-patient affordance.
 *
 * Non-enumeration (ADR-0012): POST /clinic/invitations answers an identical
 * 202 whether or not the email matched a patient account, and this screen
 * shows ONE fixed sentence for every successful send — the UI must never
 * imply it knows whether the email matched.
 */

import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { messageFor } from '../../api/client';
import { getPanel, invitePatient } from '../../api/endpoints';
import type { PanelPatientOut } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { formatDayYear, initials } from '../../lib/format';
import { useApi } from '../../lib/useApi';

/** The only success sentence this screen ever shows — matched or not. */
export const INVITE_SENT_MESSAGE =
  "If that email belongs to a patient account, they'll receive an invitation.";

function PanelRow({ patient }: { patient: PanelPatientOut }) {
  return (
    <Link className="prow" to={`/clinic/patients/${encodeURIComponent(patient.patient_id)}`}>
      <span className="ava" aria-hidden="true">
        {initials(patient.display_name)}
      </span>
      <span className="nm">
        <b>{patient.display_name}</b>
        <small>Consented {formatDayYear(Date.parse(patient.consent_granted_at))}</small>
      </span>
      <span className="pill on">Connected</span>
    </Link>
  );
}

function InviteCard() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setSent(false);
    setError(null);
    try {
      await invitePatient(email);
      setSent(true);
      setEmail('');
    } catch (cause) {
      setError(messageFor(cause));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card">
      <h2>Invite a patient</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        They appear on your panel only after they approve the connection — consent gates every data
        flow.
      </p>
      {sent && <SuccessNotice>{INVITE_SENT_MESSAGE}</SuccessNotice>}
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      <form
        onSubmit={(event) => {
          void onSubmit(event);
        }}
      >
        <div className="field">
          <label htmlFor="invite-email">Patient email</label>
          <input
            id="invite-email"
            type="email"
            autoComplete="off"
            required
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
          />
        </div>
        <button className="btn secondary" type="submit" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send invitation'}
        </button>
      </form>
    </div>
  );
}

export function PanelPage() {
  const { data: panel, error, loading } = useApi(getPanel);

  if (loading) {
    return <Loading label="Loading your panel…" />;
  }
  if (error !== null || panel === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  return (
    <div>
      <h1>Your panel</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        Patients who have consented to share their data with your clinic.
      </p>
      <div className="card">
        {panel.patients.length === 0 ? (
          <div className="empty-state">
            <p style={{ marginTop: 0 }}>
              <b>No consented patients yet.</b>
            </p>
            <p style={{ marginBottom: 0 }}>
              Invite a patient below — they appear here once they approve the connection.
            </p>
          </div>
        ) : (
          panel.patients.map((patient) => <PanelRow key={patient.patient_id} patient={patient} />)
        )}
      </div>
      <InviteCard />
    </div>
  );
}
