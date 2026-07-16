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

/** ConfidenceLevel — how much to trust the Index (coverage + recency), NOT health. */
export type ConfidenceLevel = 'high' | 'medium' | 'low';

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
  /** Neuropathy Status Index (ADR-0034) — a non-diagnostic 0-100 composite, higher =
   *  better. `score` is null when no domain is present (the "not enough data" state).
   *  The card's single source of truth: `score` + its OWN `score_delta_30d` + Confidence,
   *  anchored to a real `as_of` date. Card colour AND arrow are both driven by the delta,
   *  so they can never contradict. */
  score: number | null;
  score_delta_30d: number | null;
  as_of: string | null;
  confidence_level: ConfidenceLevel | null;
  direction_word: Direction | null;
  data_is_stale: boolean;
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
  /** 0-10 pain NRS + 0-10 numbness/tingling severity (ADR-0034 Phase 1). Higher =
   *  worse. Optional and persisted only when the `ingest_symptoms` capability is on;
   *  the server ignores them when it is off (enforced-flag honesty, ADR-0013). */
  pain?: number | null;
  numbness?: number | null;
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

// ---- emr.py (ADR-0028 — patient EMR connect) ----

/** ProviderOut */
export interface EmrProviderOut {
  key: string;
  name: string;
  vendor: string;
  sandbox_fhir_base: string | null;
  note: string;
}

/** ConnectStartIn */
export interface EmrConnectStartIn {
  provider_key?: string | null;
  fhir_base?: string | null;
}

/** ConnectStartOut */
export interface EmrConnectStartOut {
  connection_id: string;
  /** Open this in the patient's browser (system browser on native). */
  authorize_url: string;
  state: string;
}

/** ConnectionOut (EMR connection — schemas/emr.py; distinct from the clinic ConnectionOut) */
export interface EmrConnectionOut {
  id: string;
  patient_id: string;
  fhir_base: string;
  provider_name: string | null;
  status: string;
  granted_scope: string | null;
  patient_fhir_id: string | null;
  token_expires_at: string | null;
  revoked_at: string | null;
}

/** LabResultIn (schemas/lab.py — the pull echoes the fetched lab results) */
export interface EmrLabResult {
  loinc_code: string;
  source_record_id: string | null;
  display: string;
  value: number | null;
  value_text: string | null;
  unit: string | null;
  effective_at: string;
  issued_at: string | null;
  status: string;
  reference_range: { low: number | null; high: number | null; unit: string | null } | null;
  interpretation: string | null;
  code_system: string;
  unit_system: string;
}

/** PullOut */
export interface EmrPullOut {
  imported: number;
  results: EmrLabResult[];
}

// ---- export.py (ADR-0031 — "Download my data") ----

/** ExportAccountProfile — the auth identity, NEVER the password hash. */
export interface ExportAccountProfile {
  display_name: string;
  email: string;
  role: string;
  created_at: string | null;
}

/** ExportPatient — the linked clinical record's non-secret fields. */
export interface ExportPatient {
  patient_id: string;
  display_name: string;
  connection_mode: string;
  created_at: string | null;
}

/** ExportObservation — one research-grade observation with full provenance. */
export interface ExportObservation {
  id: string;
  source: string;
  origin: string;
  code: string;
  code_system: string | null;
  value_num: number | null;
  value_text: string | null;
  unit: string | null;
  unit_system: string | null;
  effective_at: string;
  recorded_at: string;
  status: string;
  revises_id: string | null;
  recorded_by_role: string | null;
  quality: Record<string, unknown>;
  payload: Record<string, unknown>;
}

/** ExportOut — the complete "Download my data" envelope. NEVER carries tokens,
 *  secrets, or the password hash (the shapes above have no field for them). */
export interface ExportOut {
  exported_at: string;
  schema_version: string;
  subject_id: string;
  account: ExportAccountProfile;
  patient: ExportPatient;
  observations: ExportObservation[];
  trajectory: Trajectory;
  capabilities: CapabilityStateOut[];
  clinic_connections: ConnectionOut[];
  emr_connections: EmrConnectionOut[];
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
