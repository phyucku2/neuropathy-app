/**
 * The complete API surface the patient UI talks to — one typed function per
 * backend route (backend/app/api/routes/). Nothing else is ever called.
 */

import { request } from './client';
import type {
  AdlCheckInIn,
  AdlCheckInOut,
  BiomechImportOut,
  CapabilitiesOut,
  CapabilityStateOut,
  ConnectionOut,
  LoginIn,
  MeOut,
  ObservationPage,
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

// ---- trajectory ----

export function getTrajectory(): Promise<Trajectory> {
  return request<Trajectory>('/trajectory');
}

// ---- observations / ADL ----

export function getObservations(params?: {
  code?: string;
  limit?: number;
  offset?: number;
}): Promise<ObservationPage> {
  const query = new URLSearchParams();
  if (params?.code !== undefined) query.set('code', params.code);
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  const suffix = query.size > 0 ? `?${query.toString()}` : '';
  return request<ObservationPage>(`/observations${suffix}`);
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
