/**
 * API contracts — TypeScript mirrors of the backend Pydantic schemas.
 *
 * Each type maps 1:1 to a schema in backend/app/schemas/ (named in the comment
 * above it). The UI talks ONLY to these endpoints; keep this file in lockstep
 * with the backend contracts (ADR-0015).
 */

// ---- auth.py ----

/** RegisterIn */
export interface RegisterIn {
  email: string;
  password: string;
  display_name: string;
}

/** LoginIn */
export interface LoginIn {
  email: string;
  password: string;
}

/** TokenOut */
export interface TokenOut {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/** AccessTokenOut */
export interface AccessTokenOut {
  access_token: string;
  token_type: string;
}

/** MeOut */
export interface MeOut {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  patient_id: string | null;
}

// ---- trajectory.py ----

/** Direction */
export type Direction = 'improving' | 'stable' | 'declining' | 'insufficient_data';

/** SignalTrend */
export interface SignalTrend {
  code: string;
  source: string;
  direction: Direction;
  detail: string;
}

/** Trajectory */
export interface Trajectory {
  direction: Direction;
  confidence: number;
  summary: string;
  signals: SignalTrend[];
  data_gaps: string[];
  narrative_source: string;
}

// ---- ingestion.py ----

/** ObservationItem */
export interface ObservationItem {
  code: string;
  display: string | null;
  value: number | null;
  value_text: string | null;
  unit: string | null;
  effective_at: string;
  source: string;
  status: string;
}

/** ObservationPage */
export interface ObservationPage {
  items: ObservationItem[];
  total: number;
  limit: number;
  offset: number;
}

/** AdlCheckInIn */
export interface AdlCheckInIn {
  walking: number;
  stairs: number;
  balance_confidence: number;
  check_in_date?: string | null;
}

/** AdlCheckInOut */
export interface AdlCheckInOut {
  check_in_date: string;
  daily_score: number;
  superseded: boolean;
}

// ---- biomech.py ----

/** BiomechImportOut */
export interface BiomechImportOut {
  report_kind: string | null;
  assessment_at: string | null;
  imported: number;
  skipped: number;
  warnings: string[];
}

// ---- capability.py ----

/** CapabilityStateOut */
export interface CapabilityStateOut {
  key: string;
  name: string;
  active: boolean;
  managed_by: 'patient' | 'clinic';
  expires_at: string | null;
  enforced: boolean;
}

/** CapabilitiesOut */
export interface CapabilitiesOut {
  capabilities: CapabilityStateOut[];
}

/** CapabilitySetIn */
export interface CapabilitySetIn {
  active: boolean;
}

/** ClinicianCapabilitySetIn — expiry pairs only with active=true (the backend 422s otherwise). */
export interface ClinicianCapabilitySetIn {
  active: boolean;
  expires_at?: string | null;
}

// ---- clinic.py ----

/** ConnectionOut (patient-side clinic connection) */
export interface ConnectionOut {
  id: string;
  clinic_id: string;
  clinic_name: string;
  status: string;
  initiated_by: string;
  consent_granted_at: string | null;
  revoked_at: string | null;
}

/** InvitationIn */
export interface InvitationIn {
  email: string;
}

/** InvitationOut — one fixed sentence for every outcome (non-enumeration). */
export interface InvitationOut {
  detail: string;
}

/** PanelPatientOut */
export interface PanelPatientOut {
  patient_id: string;
  display_name: string;
  connection_id: string;
  consent_granted_at: string;
}

/** PanelOut */
export interface PanelOut {
  patients: PanelPatientOut[];
}
