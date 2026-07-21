/**
 * The complete API surface the app talks to — one typed function per backend
 * route (backend/app/api/routes/), patient and clinician areas alike. Nothing
 * else is ever called.
 */

import { request } from './client';
import type {
  AdlCheckInIn,
  AdlCheckInOut,
  BiomechImportOut,
  CapabilitiesOut,
  CapabilityStateOut,
  CaregiverClaimOut,
  CaregiverInviteCreateOut,
  CaregiverInviteOut,
  CaregiverPatientsOut,
  CaregiverRegisterIn,
  CaregiverScope,
  ClinicianCapabilitySetIn,
  ConnectionOut,
  EmrConnectionOut,
  EmrConnectStartIn,
  EmrConnectStartOut,
  EmrProviderOut,
  EmrPullNotesOut,
  EmrPullOut,
  EventIn,
  EventList,
  EventOut,
  ExportOut,
  InvitationOut,
  LoginIn,
  LoginOut,
  MedicationChangeIn,
  MedicationChangeOut,
  MedicationLog,
  MedicationRegisterIn,
  MeOut,
  MfaEnrollOut,
  MfaPendingOut,
  MfaStatusOut,
  MfaVerifyIn,
  ObservationPage,
  PanelOut,
  PatientCaregiverLinkOut,
  RegisterIn,
  TokenOut,
  Trajectory,
  VisitSummary,
  WearableImportOut,
  WearableSampleIn,
} from './types';

// ---- auth ----

export function login(body: LoginIn): Promise<LoginOut> {
  return request<LoginOut>('/auth/login', { method: 'POST', body, anonymous: true });
}

/** Whether /auth/login answered the MFA step-up instead of full tokens (§1B C6). */
export function isMfaPending(result: LoginOut): result is MfaPendingOut {
  return 'mfa_pending_token' in result;
}

// ---- MFA (TOTP) for clinician/ops accounts (§1B C6) ----

/** Whether the signed-in account has a confirmed authenticator factor. */
export function getMfaStatus(): Promise<MfaStatusOut> {
  return request<MfaStatusOut>('/auth/mfa');
}

/**
 * Start enrollment: the backend mints a TOTP secret (stored ONLY vault-encrypted server
 * side) and returns the otpauth:// URI + secret ONCE for the authenticator app. The UI
 * shows it a single time and drops it after confirmation — there is no re-read endpoint.
 */
export function enrollMfa(): Promise<MfaEnrollOut> {
  return request<MfaEnrollOut>('/auth/mfa/enroll', { method: 'POST' });
}

/** Prove the authenticator holds the secret: a current 6-digit code activates the factor. */
export function confirmMfaEnrollment(code: string): Promise<MfaStatusOut> {
  return request<MfaStatusOut>('/auth/mfa/enroll/confirm', { method: 'POST', body: { code } });
}

/**
 * The login step-up: exchange the short-lived mfa_pending token + the 6-digit code for
 * the real tokens. Anonymous — the pending token rides in the BODY, never as a bearer
 * (it is not an access token, and the backend enforces the kind distinction).
 */
export function verifyMfa(body: MfaVerifyIn): Promise<TokenOut> {
  return request<TokenOut>('/auth/mfa/verify', { method: 'POST', body, anonymous: true });
}

export function register(body: RegisterIn): Promise<TokenOut> {
  return request<TokenOut>('/auth/register', { method: 'POST', body, anonymous: true });
}

export function getMe(): Promise<MeOut> {
  return request<MeOut>('/auth/me');
}

/**
 * Permanently delete the signed-in patient's account and ALL health data
 * (ADR-0027). Requires the password as fresh re-authentication — a bearer token
 * alone must never destroy an account. 204 on success; 403 with a verbatim-shown
 * detail when the password doesn't match (nothing is deleted then).
 */
export async function deleteAccount(password: string): Promise<void> {
  await request<unknown>('/auth/me', { method: 'DELETE', body: { password } });
}

/**
 * Download the signed-in patient's COMPLETE record (ADR-0031) — the right-of-access
 * companion to account deletion. The backend audits every export and NEVER includes a
 * token, secret, or password hash in the payload. Patient role only (403 otherwise).
 */
export function exportMyData(): Promise<ExportOut> {
  return request<ExportOut>('/me/export');
}

/**
 * The patient-held Visit-Ready Summary (ADR-0045) — a windowed, curated re-presentation of
 * the signed-in patient's own analyzable record, the SAME assembly the clinician view answers
 * from. `window` must be one of 30/60/90/120/365 (the backend 422s anything else). Patient
 * role only (403 otherwise); the response is PHI, served Cache-Control: no-store.
 */
export function getMyVisitSummary(windowDays: number): Promise<VisitSummary> {
  return request<VisitSummary>(`/me/visit-summary?window=${String(windowDays)}`);
}

// ---- trajectory ----

export function getTrajectory(): Promise<Trajectory> {
  return request<Trajectory>('/trajectory');
}

// ---- observations / ADL ----

export interface ObservationQuery {
  code?: string;
  limit?: number;
  offset?: number;
}

function observationQuerySuffix(params?: ObservationQuery): string {
  const query = new URLSearchParams();
  if (params?.code !== undefined) query.set('code', params.code);
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  return query.size > 0 ? `?${query.toString()}` : '';
}

export function getObservations(params?: ObservationQuery): Promise<ObservationPage> {
  return request<ObservationPage>(`/observations${observationQuerySuffix(params)}`);
}

export function postAdlCheckIn(body: AdlCheckInIn): Promise<AdlCheckInOut> {
  return request<AdlCheckInOut>('/adl', { method: 'POST', body });
}

// ---- BioMech report upload ----

export function uploadBiomechReport(file: File): Promise<BiomechImportOut> {
  const formData = new FormData();
  formData.append('file', file);
  return request<BiomechImportOut>('/biomech/reports', { method: 'POST', formData });
}

// ---- medications & between-visit events/notes (ADR-0045 P2) ----

/**
 * Idempotency key for one compose action (ADR-0045 P2). The client mints it so a single
 * network retry (e.g. the 401-refresh replay in client.ts, which resends the SAME serialized
 * body) folds to a graceful `add_if_absent` skip; a fresh user submission is a fresh action.
 */
function clientEntryId(): string {
  return crypto.randomUUID();
}

/** Register a NEW medication/supplement — the server mints `med:{uuid}` and writes the
 * `added` entry. Patient role only, capability-gated (`ingest_medications`, 409 when off). */
export function postMedication(
  body: Omit<MedicationRegisterIn, 'client_entry_id'>,
): Promise<MedicationChangeOut> {
  return request<MedicationChangeOut>('/medications', {
    method: 'POST',
    body: { ...body, client_entry_id: clientEntryId() },
  });
}

/** Append a `dose_changed` or `stopped` entry to an existing medication's log. 404 (never
 * 403) when the patient owns no medication with this id (no existence leak). */
export function postMedicationChange(
  medicationId: string,
  body: Omit<MedicationChangeIn, 'client_entry_id'>,
): Promise<MedicationChangeOut> {
  return request<MedicationChangeOut>(`/medications/${encodeURIComponent(medicationId)}/changes`, {
    method: 'POST',
    body: { ...body, client_entry_id: clientEntryId() },
  });
}

/** The patient's folded current medication list + per-med change log, active-first. PHI. */
export function getMedications(): Promise<MedicationLog> {
  return request<MedicationLog>('/medications');
}

/** Record one between-visit event/note. Capability-gated (`ingest_events`, 409 when off). */
export function postEvent(body: Omit<EventIn, 'client_entry_id'>): Promise<EventOut> {
  return request<EventOut>('/events', {
    method: 'POST',
    body: { ...body, client_entry_id: clientEntryId() },
  });
}

/** The patient's between-visit events & notes, newest-first. PHI. */
export function getEvents(): Promise<EventList> {
  return request<EventList>('/events');
}

// ---- wearable/phone mobility import (ADR-0035 Phase 1) ----

export function importWearable(samples: WearableSampleIn[]): Promise<WearableImportOut> {
  return request<WearableImportOut>('/wearable', { method: 'POST', body: { samples } });
}

// ---- capabilities ----

export function getCapabilities(): Promise<CapabilitiesOut> {
  return request<CapabilitiesOut>('/capabilities');
}

export function putCapability(key: string, active: boolean): Promise<CapabilityStateOut> {
  return request<CapabilityStateOut>(`/capabilities/${encodeURIComponent(key)}`, {
    method: 'PUT',
    body: { active },
  });
}

// ---- clinic connections ----

export function getConnections(): Promise<ConnectionOut[]> {
  return request<ConnectionOut[]>('/connections');
}

export function grantConsent(connectionId: string): Promise<ConnectionOut> {
  return request<ConnectionOut>(`/connections/${encodeURIComponent(connectionId)}/consent`, {
    method: 'POST',
  });
}

export async function revokeConnection(connectionId: string): Promise<void> {
  await request<unknown>(`/connections/${encodeURIComponent(connectionId)}`, { method: 'DELETE' });
}

// ---- EMR connections (SMART on FHIR — ADR-0008/0009/0028) ----

export function getEmrProviders(q = ''): Promise<EmrProviderOut[]> {
  const suffix = q !== '' ? `?q=${encodeURIComponent(q)}` : '';
  return request<EmrProviderOut[]>(`/emr/providers${suffix}`);
}

/** Start the SMART handshake: the backend does discovery + PKCE and returns the
 * authorize URL to open plus the `state` the callback must echo. */
export function startEmrConnect(body: EmrConnectStartIn): Promise<EmrConnectStartOut> {
  return request<EmrConnectStartOut>('/emr/connect', { method: 'POST', body });
}

/**
 * Relay the EMR's redirect back to the backend (ADR-0028): GET /emr/callback is
 * bearer-authenticated, so the EHR's browser redirect cannot reach it directly —
 * the SPA's /emr/callback route forwards code+state with the patient's token and
 * the backend exchanges the code (PKCE) and activates the connection.
 */
export function completeEmrCallback(state: string, code: string): Promise<EmrConnectionOut> {
  const query = new URLSearchParams({ state, code });
  return request<EmrConnectionOut>(`/emr/callback?${query.toString()}`);
}

export function pullEmrLabs(connectionId: string): Promise<EmrPullOut> {
  return request<EmrPullOut>(`/emr/connections/${encodeURIComponent(connectionId)}/pull`, {
    method: 'POST',
  });
}

/** Pull clinical-note METADATA from the EMR (ADR-0045 P2 #27). Gated by the opt-in
 * `ingest_notes` capability; the response is counts only (no note text ever leaves the
 * backend). The note body is opened on demand, never during this poll. */
export function pullEmrClinicalNotes(connectionId: string): Promise<EmrPullNotesOut> {
  return request<EmrPullNotesOut>(
    `/emr/connections/${encodeURIComponent(connectionId)}/pull-notes`,
    { method: 'POST' },
  );
}

/** Revoke: the backend flips the status AND deletes the vaulted tokens (ADR-0017). */
export function revokeEmrConnection(connectionId: string): Promise<EmrConnectionOut> {
  return request<EmrConnectionOut>(`/emr/connections/${encodeURIComponent(connectionId)}`, {
    method: 'DELETE',
  });
}

// ---- caregiver companion (ADR-0047 Phase A) ----

/**
 * Caregiver self-registration — ONLY with a valid invite code (the code is judged before
 * the account is created; a dead code answers 404 with one fixed message). Anonymous.
 * Success creates a PENDING link: nothing is visible until the patient accepts.
 */
export function registerCaregiver(body: CaregiverRegisterIn): Promise<TokenOut> {
  return request<TokenOut>('/caregiver/register', { method: 'POST', body, anonymous: true });
}

/** An existing caregiver claims another patient's code. NON-ENUMERATING: the 202 body is
 *  byte-identical whether or not the code matched; a match creates a PENDING link the
 *  patient must accept before anything is visible (double opt-in). */
export function claimCaregiverCode(code: string): Promise<CaregiverClaimOut> {
  return request<CaregiverClaimOut>('/caregiver/claims', { method: 'POST', body: { code } });
}

/** The caregiver's shared patients — accepted, non-revoked links only. PHI, no-store. */
export function getCaregiverPatients(): Promise<CaregiverPatientsOut> {
  return request<CaregiverPatientsOut>('/caregiver/patients');
}

/** The shared patient's DETERMINISTIC trajectory (trends scope suffices). A patient this
 *  caregiver may not read answers 404, indistinguishable from nonexistent. */
export function getCaregiverPatientTrajectory(patientId: string): Promise<Trajectory> {
  return request<Trajectory>(`/caregiver/patients/${encodeURIComponent(patientId)}/trajectory`);
}

/** The shared patient's Visit-Ready Summary — FULL scope only; a trends-scope caller gets
 *  the same 404 as a nonexistent patient. `window` must be one of 30/60/90/120/365. */
export function getCaregiverPatientVisitSummary(
  patientId: string,
  windowDays: number,
): Promise<VisitSummary> {
  return request<VisitSummary>(
    `/caregiver/patients/${encodeURIComponent(patientId)}/visit-summary?window=${String(windowDays)}`,
  );
}

/** Generate a share code for a loved one. The plaintext code appears in THIS response
 *  only — it is stored hashed server-side and can never be re-read. */
export function createCaregiverInvite(): Promise<CaregiverInviteCreateOut> {
  return request<CaregiverInviteCreateOut>('/me/caregiver-invites', { method: 'POST' });
}

/** The patient's still-claimable invites (the codes themselves are unrecoverable). */
export function getCaregiverInvites(): Promise<CaregiverInviteOut[]> {
  return request<CaregiverInviteOut[]>('/me/caregiver-invites');
}

/** Cancel the patient's own invite: the code dies immediately. */
export async function cancelCaregiverInvite(inviteId: string): Promise<void> {
  await request<unknown>(`/me/caregiver-invites/${encodeURIComponent(inviteId)}`, {
    method: 'DELETE',
  });
}

/** The patient's caregiver links — pending requests, active caregivers, revoked history. */
export function getCaregiverLinks(): Promise<PatientCaregiverLinkOut[]> {
  return request<PatientCaregiverLinkOut[]>('/me/caregivers');
}

/** Accept a pending caregiver request — the double opt-in's second step; only now does
 *  anything become visible (ADR-0047). */
export function acceptCaregiverLink(linkId: string): Promise<PatientCaregiverLinkOut> {
  return request<PatientCaregiverLinkOut>(`/me/caregivers/${encodeURIComponent(linkId)}/accept`, {
    method: 'POST',
  });
}

/** Decline a pending caregiver request: the link dies without ever having been readable. */
export async function declineCaregiverLink(linkId: string): Promise<void> {
  await request<unknown>(`/me/caregivers/${encodeURIComponent(linkId)}/decline`, {
    method: 'POST',
  });
}

/** Change what THIS caregiver can see (trends <-> full) — effective on their next read. */
export function setCaregiverScope(
  linkId: string,
  scope: CaregiverScope,
): Promise<PatientCaregiverLinkOut> {
  return request<PatientCaregiverLinkOut>(`/me/caregivers/${encodeURIComponent(linkId)}`, {
    method: 'PATCH',
    body: { scope },
  });
}

/** Revoke a caregiver's access: it stops immediately and nothing can block it (ADR-0047). */
export async function revokeCaregiverLink(linkId: string): Promise<void> {
  await request<unknown>(`/me/caregivers/${encodeURIComponent(linkId)}`, { method: 'DELETE' });
}

// ---- clinician surface (ADR-0012 / ADR-0013) ----

/** Non-enumerating 202: the response is identical whether or not the email matched. */
export function invitePatient(email: string): Promise<InvitationOut> {
  return request<InvitationOut>('/clinic/invitations', { method: 'POST', body: { email } });
}

export function getPanel(): Promise<PanelOut> {
  return request<PanelOut>('/clinic/patients');
}

function clinicPatientPath(patientId: string, suffix: string): string {
  return `/clinic/patients/${encodeURIComponent(patientId)}${suffix}`;
}

/** DETERMINISTIC only — the backend never narrates the clinician view (ADR-0012). */
export function getClinicPatientTrajectory(patientId: string): Promise<Trajectory> {
  return request<Trajectory>(clinicPatientPath(patientId, '/trajectory'));
}

/**
 * The clinician-side Visit-Ready Summary (ADR-0045) — the SAME VisitSummary shape/data as the
 * patient print, behind the consented-connection gate (non-enumerating 404, never 403). Always
 * deterministic (no narrator). `window` must be one of 30/60/90/120/365.
 */
export function getClinicPatientVisitSummary(
  patientId: string,
  windowDays: number,
): Promise<VisitSummary> {
  return request<VisitSummary>(
    clinicPatientPath(patientId, `/visit-summary?window=${String(windowDays)}`),
  );
}

export function getClinicPatientObservations(
  patientId: string,
  params?: ObservationQuery,
): Promise<ObservationPage> {
  return request<ObservationPage>(
    clinicPatientPath(patientId, `/observations${observationQuerySuffix(params)}`),
  );
}

export function getClinicPatientCapabilities(patientId: string): Promise<CapabilitiesOut> {
  return request<CapabilitiesOut>(clinicPatientPath(patientId, '/capabilities'));
}

/** Order-style set/renew: expiry pairs only with active=true (the backend 422s otherwise). */
export function putClinicPatientCapability(
  patientId: string,
  key: string,
  body: ClinicianCapabilitySetIn,
): Promise<CapabilityStateOut> {
  return request<CapabilityStateOut>(
    clinicPatientPath(patientId, `/capabilities/${encodeURIComponent(key)}`),
    { method: 'PUT', body },
  );
}
