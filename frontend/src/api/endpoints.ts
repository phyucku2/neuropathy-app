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
  ClinicianCapabilitySetIn,
  ConnectionOut,
  EmrConnectionOut,
  EmrConnectStartIn,
  EmrConnectStartOut,
  EmrProviderOut,
  EmrPullOut,
  ExportOut,
  InvitationOut,
  LoginIn,
  MeOut,
  ObservationPage,
  PanelOut,
  RegisterIn,
  TokenOut,
  Trajectory,
} from './types';

// ---- auth ----

export function login(body: LoginIn): Promise<TokenOut> {
  return request<TokenOut>('/auth/login', { method: 'POST', body, anonymous: true });
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

/** Revoke: the backend flips the status AND deletes the vaulted tokens (ADR-0017). */
export function revokeEmrConnection(connectionId: string): Promise<EmrConnectionOut> {
  return request<EmrConnectionOut>(`/emr/connections/${encodeURIComponent(connectionId)}`, {
    method: 'DELETE',
  });
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
