/**
 * Enter another patient's invite code (ADR-0047) — the signed-in caregiver's claim
 * form, used on the caregiver home for both the first link's waiting state and
 * "add another patient".
 *
 * The 202 answer is ONE fixed sentence whether or not the code matched (the server
 * never reveals whether a code exists) — shown verbatim, because the honest state
 * after a claim is "waiting for the patient's approval", never "linked".
 */

import { useState, type FormEvent } from 'react';
import { messageFor } from '../../api/client';
import { claimCaregiverCode } from '../../api/endpoints';
import { ErrorNotice, SuccessNotice } from '../../components/StatusMessages';

export function ClaimCodeCard({ onClaimed }: { onClaimed?: () => void }) {
  const [code, setCode] = useState('');
  const [detail, setDetail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setDetail(null);
    try {
      const result = await claimCaregiverCode(code.trim());
      setDetail(result.detail);
      setCode('');
      onClaimed?.();
    } catch (cause) {
      // e.g. the claim throttle's 429 — the server's own wording, verbatim.
      setError(messageFor(cause));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="card" aria-labelledby="claim-code-heading">
      <h2 id="claim-code-heading">Have an invite code?</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        Enter the code your loved one shared with you. They still have to approve it — nothing is
        visible until they say yes.
      </p>
      {detail !== null && <SuccessNotice>{detail}</SuccessNotice>}
      {error !== null && <ErrorNotice>{error}</ErrorNotice>}
      <form
        onSubmit={(event) => {
          void onSubmit(event);
        }}
      >
        <div className="field">
          <label htmlFor="claim-code">Invite code</label>
          <input
            id="claim-code"
            type="text"
            autoComplete="off"
            required
            maxLength={64}
            value={code}
            onChange={(event) => {
              setCode(event.target.value);
            }}
          />
        </div>
        <button className="btn" type="submit" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send my request'}
        </button>
      </form>
    </section>
  );
}
