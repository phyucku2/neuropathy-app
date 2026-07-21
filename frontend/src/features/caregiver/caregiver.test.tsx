/**
 * Caregiver Companion Phase A (ADR-0047): role-aware routing, the join (register-
 * with-code) flow, the home trend view with the persistent 911 banner and the
 * co-located non-diagnostic note, the claim flow's honest waiting state, and the
 * full-scope read-only Visit-Ready Summary with its neutral not-available state.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import {
  CAREGIVER_CLAIM_ACCEPTED_DETAIL,
  CAREGIVER_CODE_INVALID_DETAIL,
  CAREGIVER_EMERGENCY_NOTICE,
  CAREGIVER_PATIENTS_EMPTY,
  CAREGIVER_PATIENTS_TRENDS_ONLY,
  CAREGIVER_SHARED_PATIENT,
  TEST_CAREGIVER_CODE,
} from '../../test/fixtures';
import { renderApp } from '../../test/renderApp';
import { actAsCaregiver, server } from '../../test/server';

/** The banner rendered by the caregiver AppShell (the wording is the component's own;
 *  the backend's EMERGENCY_NOTICE constant carries the same framing). */
const BANNER_TEXT = /If something's wrong right now, call 911/;

describe('role-aware routing (ADR-0047)', () => {
  it('sends a signed-in caregiver from the patient home to /caregiver', async () => {
    actAsCaregiver();
    renderApp('/');
    expect(await screen.findByRole('heading', { name: "How they're doing" })).toBeInTheDocument();
    // The caregiver frame: marked header, no patient tab bar, persistent 911 banner.
    expect(screen.getByText('◍ Neuropathy · Caregiver')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main' })).not.toBeInTheDocument();
    expect(screen.getByText(BANNER_TEXT)).toBeInTheDocument();
  });

  it('keeps a patient out of the caregiver area', async () => {
    renderApp('/caregiver');
    // Redirected to the patient home (the trajectory hero), never the caregiver frame.
    expect(await screen.findByText('30 Day Score')).toBeInTheDocument();
    expect(screen.queryByText('◍ Neuropathy · Caregiver')).not.toBeInTheDocument();
  });
});

describe('caregiver home', () => {
  it('shows the shared patient’s trend with the co-located non-diagnostic note', async () => {
    actAsCaregiver();
    renderApp('/caregiver');
    expect(await screen.findByText('30 Day Score')).toBeInTheDocument();
    // The deterministic hero — score + direction, same computation as everywhere.
    expect(screen.getByText('74')).toBeInTheDocument();
    // Non-diagnostic + non-monitoring framing rides RIGHT NEXT to the trend.
    expect(screen.getByText(/not a diagnosis, and not live monitoring/)).toBeInTheDocument();
    // Full scope offers the read-only Visit-Ready Summary.
    expect(screen.getByRole('link', { name: 'See their Visit-Ready Summary' })).toBeInTheDocument();
    // The persistent 911 banner (rendered by the shell, on every caregiver screen).
    expect(screen.getByText(BANNER_TEXT)).toBeInTheDocument();
  });

  it('offers NO summary link at trends-only scope', async () => {
    actAsCaregiver();
    server.use(
      http.get('/caregiver/patients', () => HttpResponse.json(CAREGIVER_PATIENTS_TRENDS_ONLY)),
    );
    renderApp('/caregiver');
    expect(await screen.findByText('30 Day Score')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'See their Visit-Ready Summary' }),
    ).not.toBeInTheDocument();
  });

  it('shows the honest waiting state when no one shares yet, and claims a code', async () => {
    actAsCaregiver();
    server.use(
      http.get('/caregiver/patients', () => HttpResponse.json(CAREGIVER_PATIENTS_EMPTY)),
      http.post('/caregiver/claims', () =>
        HttpResponse.json({ detail: CAREGIVER_CLAIM_ACCEPTED_DETAIL }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/caregiver');
    expect(
      await screen.findByRole('heading', { name: 'No one is sharing with you yet' }),
    ).toBeInTheDocument();
    // Double opt-in honesty: waiting for the patient's approval, nothing visible before.
    expect(screen.getByText(/waiting for their approval/)).toBeInTheDocument();
    await user.type(screen.getByLabelText('Invite code'), TEST_CAREGIVER_CODE);
    await user.click(screen.getByRole('button', { name: 'Send my request' }));
    // The 202's single fixed sentence, verbatim (non-enumerating by design).
    expect(await screen.findByText(CAREGIVER_CLAIM_ACCEPTED_DETAIL)).toBeInTheDocument();
  });

  it('lets the caregiver pick between several patients; a revoked one is neutral', async () => {
    actAsCaregiver();
    server.use(
      http.get('/caregiver/patients', () =>
        HttpResponse.json({
          patients: [
            CAREGIVER_SHARED_PATIENT,
            {
              ...CAREGIVER_SHARED_PATIENT,
              patient_id: '99999999-0000-4000-8000-000000000000',
              link_id: '99999999-0000-4000-8000-000000000001',
              display_name: 'Sam Example',
              scope: 'trends',
            },
          ],
          emergency_notice: CAREGIVER_EMERGENCY_NOTICE,
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/caregiver');
    const picker = await screen.findByRole('group', { name: 'Choose a person' });
    expect(within(picker).getAllByRole('button')).toHaveLength(2);
    expect(await screen.findByText('30 Day Score')).toBeInTheDocument();
    // The second patient's trajectory answers 404 (revoked/unknown — indistinguishable):
    // the neutral not-available state, with no reason given.
    await user.click(within(picker).getByRole('button', { name: 'Sam Example' }));
    expect(
      await screen.findByRole('heading', { name: "This isn't available right now" }),
    ).toBeInTheDocument();
  });
});

describe('caregiver join (register with a code)', () => {
  async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, code: string) {
    await user.type(screen.getByLabelText('Invite code'), code);
    await user.type(screen.getByLabelText('Your name'), 'Casey Example');
    await user.type(screen.getByLabelText('Email'), 'casey.example@example.com');
    await user.type(screen.getByLabelText('Password'), 'synthetic-test-passphrase');
    await user.click(screen.getByRole('button', { name: 'Create account & send request' }));
  }

  it('creates the account with a valid code and lands on the waiting home', async () => {
    actAsCaregiver();
    server.use(http.get('/caregiver/patients', () => HttpResponse.json(CAREGIVER_PATIENTS_EMPTY)));
    const user = userEvent.setup();
    renderApp('/caregiver/join', { authenticated: false });
    // The 911 banner rides the join screen too — every caregiver surface carries it.
    expect(await screen.findByText(BANNER_TEXT)).toBeInTheDocument();
    await fillAndSubmit(user, TEST_CAREGIVER_CODE);
    // Signed in and routed to the caregiver home, in its honest waiting state.
    expect(
      await screen.findByRole('heading', { name: 'No one is sharing with you yet' }),
    ).toBeInTheDocument();
  });

  it('shows the fixed dead-code message verbatim and creates nothing', async () => {
    const user = userEvent.setup();
    renderApp('/caregiver/join', { authenticated: false });
    await screen.findByLabelText('Invite code');
    await fillAndSubmit(user, 'WRONG-CODE-XXXX');
    expect(await screen.findByRole('alert')).toHaveTextContent(CAREGIVER_CODE_INVALID_DETAIL);
    // Still on the join form — no session was established.
    expect(screen.getByRole('button', { name: 'Create account & send request' })).toBeEnabled();
  });
});

describe('caregiver Visit-Ready Summary (full scope, read-only)', () => {
  it('renders the shared VisitSummaryView with a window picker', async () => {
    actAsCaregiver();
    const user = userEvent.setup();
    renderApp(`/caregiver/patients/${CAREGIVER_SHARED_PATIENT.patient_id}/summary`);
    expect(
      await screen.findByRole('heading', { name: "Pat Example's Visit-Ready Summary" }),
    ).toBeInTheDocument();
    // The SAME shared render as the patient print / clinician tab.
    expect(await screen.findByRole('heading', { name: 'What changed' })).toBeInTheDocument();
    // The co-located non-diagnostic disclaimer from the payload, verbatim.
    expect(screen.getByText(/not a diagnosis/)).toBeInTheDocument();
    // The persistent 911 banner is on this screen too.
    expect(screen.getByText(BANNER_TEXT)).toBeInTheDocument();
    // The window picker refetches; the heading is labelled from the PAYLOAD's window.
    await user.click(screen.getByRole('button', { name: '1 year' }));
    await waitFor(() => {
      expect(screen.getByText('1 year summary')).toBeInTheDocument();
    });
  });

  it('shows the neutral not-available state at trends-only scope (no scope leak)', async () => {
    actAsCaregiver();
    server.use(
      http.get('/caregiver/patients', () => HttpResponse.json(CAREGIVER_PATIENTS_TRENDS_ONLY)),
    );
    renderApp(`/caregiver/patients/${CAREGIVER_SHARED_PATIENT.patient_id}/summary`);
    expect(
      await screen.findByRole('heading', { name: "This isn't available right now" }),
    ).toBeInTheDocument();
    // Neutral: no mention of scope, permission, or the summary's existence.
    expect(screen.queryByText(/scope/i)).not.toBeInTheDocument();
  });
});
