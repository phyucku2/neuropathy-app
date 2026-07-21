/**
 * "Share with a loved one" (ADR-0047 Phase A) — the patient's caregiver-sharing
 * controls on Sources: generate a one-time invite code (shown ONCE, copyable, expiry
 * stated), cancel open invites, accept or decline pending requests (the double
 * opt-in's second step — nothing is visible until the patient says yes), and manage
 * active caregivers (scope shown in plain words, change scope, stop sharing).
 *
 * The patient controls everything: revoking stops access instantly and nothing can
 * block it. Plain 60+ language throughout; the copy says what sharing IS (a periodic
 * wellness trend) and is NOT (live monitoring, an emergency channel).
 */

import { useState } from 'react';
import { messageFor } from '../../api/client';
import {
  acceptCaregiverLink,
  cancelCaregiverInvite,
  createCaregiverInvite,
  declineCaregiverLink,
  getCaregiverInvites,
  getCaregiverLinks,
  revokeCaregiverLink,
  setCaregiverScope,
} from '../../api/endpoints';
import type { CaregiverInviteCreateOut, PatientCaregiverLinkOut } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';

/** Plain words for the scope — never the raw enum on a 60+ surface. */
function scopeLabel(scope: string): string {
  return scope === 'full' ? 'their trend and your visit summary' : 'their trend only';
}

/** One pending request: the caregiver's name + the explicit accept/decline choice. */
function PendingLinkRow({
  link,
  onChanged,
  onError,
}: {
  link: PatientCaregiverLinkOut;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
      onChanged();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="src">
        <span className="ic" style={{ background: 'var(--color-brand-sky)' }} aria-hidden="true">
          👪
        </span>
        <div className="info">
          <b>{link.caregiver_display_name}</b>
          <small>Asked to follow how you&apos;re doing. Nothing is shared until you say yes.</small>
        </div>
        <span className="pill warn">Waiting for you</span>
      </div>
      <button
        type="button"
        className="btn-inline"
        disabled={busy}
        onClick={() => {
          void act(() => acceptCaregiverLink(link.id));
        }}
      >
        Yes, share with {link.caregiver_display_name}
      </button>
      <button
        type="button"
        className="btn-inline danger"
        disabled={busy}
        onClick={() => {
          void act(() => declineCaregiverLink(link.id));
        }}
      >
        No, decline
      </button>
    </div>
  );
}

/** One active caregiver: scope in plain words, change scope, stop sharing (two-tap). */
function ActiveLinkRow({
  link,
  onChanged,
  onError,
}: {
  link: PatientCaregiverLinkOut;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);
  const full = link.scope === 'full';

  const changeScope = async () => {
    setBusy(true);
    try {
      await setCaregiverScope(link.id, full ? 'trends' : 'full');
      onChanged();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
    }
  };

  // Revocation is instant and never blockable (ADR-0047) — the two-tap confirm is the
  // only step between the patient and access stopping.
  const revoke = async () => {
    if (!confirmingRevoke) {
      setConfirmingRevoke(true);
      return;
    }
    setBusy(true);
    try {
      await revokeCaregiverLink(link.id);
      onChanged();
    } catch (cause) {
      onError(messageFor(cause));
    } finally {
      setBusy(false);
      setConfirmingRevoke(false);
    }
  };

  return (
    <div>
      <div className="src">
        <span className="ic" style={{ background: 'var(--color-action-green)' }} aria-hidden="true">
          👪
        </span>
        <div className="info">
          <b>{link.caregiver_display_name}</b>
          <small>Can see {scopeLabel(link.scope)}</small>
        </div>
        <span className="pill on">Sharing</span>
      </div>
      <button
        type="button"
        className="btn-inline"
        disabled={busy}
        onClick={() => {
          void changeScope();
        }}
      >
        {full ? 'Limit to trend only' : 'Also share your visit summary'}
      </button>
      <button
        type="button"
        className="btn-inline danger"
        disabled={busy}
        onClick={() => {
          void revoke();
        }}
      >
        {busy ? 'Stopping…' : confirmingRevoke ? 'Tap again to confirm' : 'Stop sharing'}
      </button>
    </div>
  );
}

export function CaregiverShareCard() {
  const invites = useApi(getCaregiverInvites);
  const links = useApi(getCaregiverLinks);
  const [created, setCreated] = useState<CaregiverInviteCreateOut | null>(null);
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const createCode = async () => {
    setCreating(true);
    setActionError(null);
    setCopied(false);
    try {
      // The plaintext code exists ONLY in this response — shown once, never re-readable.
      setCreated(await createCaregiverInvite());
      invites.reload();
    } catch (cause) {
      setActionError(messageFor(cause));
    } finally {
      setCreating(false);
    }
  };

  const copyCode = async () => {
    if (created === null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(created.code);
      setCopied(true);
    } catch {
      // No clipboard permission — the code is on screen to read aloud or retype.
      setActionError('Copying didn’t work on this device — you can read the code out instead.');
    }
  };

  const cancelInvite = async (inviteId: string) => {
    setActionError(null);
    try {
      await cancelCaregiverInvite(inviteId);
      if (created?.id === inviteId) {
        setCreated(null);
      }
      invites.reload();
    } catch (cause) {
      setActionError(messageFor(cause));
    }
  };

  const linkRows = links.data ?? [];
  const pending = linkRows.filter((link) => link.status === 'pending');
  const active = linkRows.filter((link) => link.status === 'active');

  return (
    <>
      <h2>Share with a loved one</h2>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          Give a family member or friend a window into how you&apos;re doing. You choose what they
          see, and you can stop sharing at any time. They see a periodic wellness trend — this is
          not live monitoring, and it is not for emergencies.
        </p>
        {actionError !== null && <ErrorNotice>{actionError}</ErrorNotice>}
        {(invites.error !== null || links.error !== null) && (
          <ErrorNotice>{invites.error ?? links.error}</ErrorNotice>
        )}
        {(invites.loading || links.loading) && <Loading label="Loading your sharing…" />}

        {created !== null && (
          <SuccessNotice>
            Your invite code is{' '}
            <b className="invite-code" style={{ fontFamily: 'monospace' }}>
              {created.code}
            </b>
            . Read it to them or send it — it works once and expires{' '}
            {formatDayYear(Date.parse(created.expires_at))}. It won&apos;t be shown again.
            <br />
            <button
              type="button"
              className="btn-inline"
              onClick={() => {
                void copyCode();
              }}
            >
              {copied ? 'Copied' : 'Copy code'}
            </button>
          </SuccessNotice>
        )}
        <button
          type="button"
          className="btn-inline"
          disabled={creating}
          onClick={() => {
            void createCode();
          }}
        >
          {creating ? 'Creating…' : 'Create an invite code'}
        </button>

        {invites.data !== null && invites.data.length > 0 && (
          <>
            <div className="eyebrow" style={{ marginTop: 12 }}>
              Open invites
            </div>
            {invites.data.map((invite) => (
              <div className="src" key={invite.id}>
                <span
                  className="ic"
                  style={{ background: 'var(--color-status-neutral)' }}
                  aria-hidden="true"
                >
                  ✉
                </span>
                <div className="info">
                  <b>Invite code</b>
                  <small>
                    Created {formatDayYear(Date.parse(invite.created_at))} · expires{' '}
                    {formatDayYear(Date.parse(invite.expires_at))}
                  </small>
                </div>
                <button
                  type="button"
                  className="btn-inline danger"
                  style={{ margin: 0 }}
                  onClick={() => {
                    void cancelInvite(invite.id);
                  }}
                >
                  Cancel
                </button>
              </div>
            ))}
          </>
        )}

        {pending.length > 0 && (
          <>
            <div className="eyebrow" style={{ marginTop: 12 }}>
              Waiting for your OK
            </div>
            {pending.map((link) => (
              <PendingLinkRow
                key={link.id}
                link={link}
                onChanged={links.reload}
                onError={setActionError}
              />
            ))}
          </>
        )}

        {active.length > 0 && (
          <>
            <div className="eyebrow" style={{ marginTop: 12 }}>
              Sharing with
            </div>
            {active.map((link) => (
              <ActiveLinkRow
                key={link.id}
                link={link}
                onChanged={links.reload}
                onError={setActionError}
              />
            ))}
          </>
        )}
      </div>
    </>
  );
}
