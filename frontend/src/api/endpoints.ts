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
