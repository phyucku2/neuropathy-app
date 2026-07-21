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

/** MfaPendingOut — password verified, 6-digit code still owed (§1B C6). The token is a
 *  distinct short-lived `mfa_pending` JWT kind: the backend refuses it as access/refresh,
 *  and the client never stores it — it only rides back in POST /auth/mfa/verify. */
export interface MfaPendingOut {
  mfa_pending_token: string;
  token_type: 'mfa_pending';
}

/** LoginOut — POST /auth/login answers full tokens, or the MFA step-up when the
 *  clinician/ops account has an enrolled authenticator factor. Patients always get
 *  TokenOut (their flow is unchanged). */
export type LoginOut = TokenOut | MfaPendingOut;

/** MfaVerifyIn — the login step-up: the pending token + the authenticator code. */
export interface MfaVerifyIn {
  mfa_pending_token: string;
  code: string;
}

/** MfaEnrollOut — the otpauth:// provisioning URI + base32 secret, returned ONCE at
 *  enrollment (the backend keeps only the vault-encrypted copy). Render, confirm, drop —
 *  never persisted client-side. */
export interface MfaEnrollOut {
  otpauth_uri: string;
  secret: string;
}

/** MfaStatusOut — whether the signed-in account has a confirmed authenticator factor. */
export interface MfaStatusOut {
  enrolled: boolean;
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
  data_is_stale: boolean;
}

// ---- visit_summary.py (ADR-0045 — the Visit-Ready Summary / clinician handout) ----

/** LeadSection — which section leads the page, computed from the window (never branched
 *  in the UI). Short windows (30/60/90) lead with the diff; 120/365 lead with the trend. */
export type LeadSection = 'what_changed' | 'trajectory';

/** SparkPoint — one plotted datum for a dependency-free sparkline. */
export interface SparkPoint {
  at: string;
  value: number;
}

/** TrendSeries — a windowed series for one signal: sparkline points + start→now, sourced.
 *  `direction` is the trajectory engine's per-signal judgment (reused, never a new stat). */
export interface TrendSeries {
  code: string;
  label: string;
  source: string;
  origin: string;
  points: SparkPoint[];
  start_value: number | null;
  start_at: string | null;
  latest_value: number | null;
  latest_at: string | null;
  direction: Direction;
}

/** PriorDelta — latest-in-window vs latest-before-window for one signal (e.g. BioMech).
 *  `direction` is the polarity-judged step prior→latest (`insufficient_data` with no prior). */
export interface PriorDelta {
  code: string;
  label: string;
  source: string;
  origin: string;
  latest_value: number | null;
  latest_at: string | null;
  prior_value: number | null;
  prior_at: string | null;
  direction: Direction;
}

/** LabDelta — most-recent-per-analyte vs the prior value, UNIT-SAFE (ADR-0015). `delta` is
 *  null whenever the prior is absent OR its unit differs (no cross-unit subtraction, ever);
 *  `unit_changed` flags the latter so the UI can say so rather than silently drop it. */
export interface LabDelta {
  code: string;
  label: string;
  source: string;
  origin: string;
  unit: string | null;
  latest_value: number | null;
  latest_at: string | null;
  prior_value: number | null;
  prior_at: string | null;
  prior_unit: string | null;
  delta: number | null;
  unit_changed: boolean;
}

/** ActivityStat — wearable / CGM summary statistics only (count + mean/min/max). */
export interface ActivityStat {
  code: string;
  label: string;
  source: string;
  origin: string;
  count: number;
  mean: number | null;
  min: number | null;
  max: number | null;
  latest_at: string | null;
}

/** AdherenceGap — check-in adherence facts: recency of the last ADL check-in + per-window counts. */
export interface AdherenceGap {
  last_checkin_at: string | null;
  days_since_last_checkin: number | null;
  checkins_in_window: number;
  checkins_in_prior_window: number;
}

/** SymptomTrendChange — a symptom's current-window trend direction vs the prior window's. */
export interface SymptomTrendChange {
  code: string;
  label: string;
  source: string;
  origin: string;
  current_direction: Direction;
  prior_direction: Direction;
  changed: boolean;
}

/** MedicationChangeDelta — one medication CHANGE ROW whose effective_at falls in the current
 *  window (ADR-0045 P2). The "recorded since last visit that may not be in your chart" safety
 *  surfacing. Purely descriptive: it names WHAT the patient recorded — NO reconciliation,
 *  interaction check, or recommendation (the hard non-diagnostic line). */
export interface MedicationChangeDelta {
  medication_id: string;
  name: string;
  kind: string;
  change_type: string;
  dose_amount: number | null;
  dose_unit: string | null;
  dose_text: string | null;
  effective_at: string;
  provenance: string;
}

/** WhatChanged — the window's deterministic diff against the prior window (the diff, not the dump). */
export interface WhatChanged {
  new_labs: LabDelta[];
  symptom_trend: SymptomTrendChange[];
  adherence: AdherenceGap;
  latest_biomech: PriorDelta[];
  medication_changes: MedicationChangeDelta[];
}

/** MedicationItem — a medication folded to its current state for the handout (ADR-0045 P2).
 *  Descriptive only; both the patient print and the consented-clinician view render this same
 *  section (one assembly, so they can never drift). */
export interface MedicationItem {
  medication_id: string;
  name: string;
  kind: string;
  status: string;
  current_dose_amount: number | null;
  current_dose_unit: string | null;
  current_dose_text: string | null;
  prescriber: string | null;
  started_on: string;
  last_change_at: string;
  provenance: string;
}

/** PatientEventItem — one between-visit event/note in the window (ADR-0045 P2), newest-first.
 *  `note` is the patient's own words, verbatim. Descriptive; no triage or red-flag scan. */
export interface PatientEventItem {
  type: string;
  display: string;
  effective_at: string;
  note: string | null;
  reviewed: boolean;
  provenance: string;
}

/** EmrNoteItem — one EMR clinician note in the window, METADATA ONLY (ADR-0045 P2 #27).
 *  NON-DIAGNOSTIC: the payload NEVER carries the note body — only type/author/date + an
 *  encounter reference. Surfaces the note's existence with an "open" affordance to the
 *  verbatim text elsewhere; it is never summarized or interpreted here. */
export interface EmrNoteItem {
  type_display: string | null;
  author_display: string | null;
  authored_at: string;
  encounter_fhir_id: string | null;
  provenance: string;
}

/** QuestionsToAsk — change-surfacing prompts about the patient's own data, templates never
 *  advice. `change_pointed` is EMPTY unless the backend feature flag is on (FDA D2 gate). */
export interface QuestionsToAsk {
  data_completeness: string[];
  change_pointed: string[];
}

/** PlaceholderRow — a forward-stable layout row for a section not yet captured (render-only, P1). */
export interface PlaceholderRow {
  key: string;
  label: string;
  status: 'not_yet_tracked';
  phase: string;
}

/** VisitSummary — the Visit-Ready Summary envelope for one patient over one window (ADR-0045 P1).
 *  It carries PHI by design and is served no-store; it makes NO clinical claim — each datum is
 *  labeled with source + origin + date, and the disclaimer/sheet-label ride in the envelope. */
export interface VisitSummary {
  generated_at: string;
  schema_version: string;
  subject_id: string;
  window_days: number;
  window_end: string;
  current_window_start: string;
  prior_window_start: string;
  lead_section: LeadSection;
  status: Trajectory;
  what_changed: WhatChanged;
  symptoms: TrendSeries[];
  function: TrendSeries[];
  balance_gait: PriorDelta[];
  labs: LabDelta[];
  activity: ActivityStat[];
  medications: MedicationItem[];
  patient_notes: PatientEventItem[];
  emr_notes: EmrNoteItem[];
  placeholders: PlaceholderRow[];
  questions: QuestionsToAsk;
  disclaimer: string;
  sheet_label: string;
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

// ---- medication.py (ADR-0045 P2 — patient-entered medication change log) ----

/** MedicationKind — closed vocabulary so the log never carries free-text categories. */
export type MedicationKind = 'prescription' | 'otc' | 'supplement';

/** MedicationChangeType — `added` is minted at registration; `dose_changed`/`stopped` append
 *  later. None supersedes another — the set of entries IS the history. */
export type MedicationChangeType = 'added' | 'dose_changed' | 'stopped';

/** MedicationStatus — current folded state; a stopped med is still shown (never dropped). */
export type MedicationStatus = 'active' | 'stopped';

/** MedicationRegisterIn — register a NEW medication/supplement (emits the `added` entry). The
 *  `client_entry_id` idempotency key is minted by the endpoint client, not the caller. */
export interface MedicationRegisterIn {
  name: string;
  kind: MedicationKind;
  dose_amount: number | null;
  dose_unit: string | null;
  dose_text: string | null;
  prescriber: string | null;
  reason: string | null;
  started_on: string;
  client_entry_id: string;
}

/** MedicationChangeIn — append a `dose_changed` or `stopped` entry to an existing med's log. */
export interface MedicationChangeIn {
  change_type: Exclude<MedicationChangeType, 'added'>;
  dose_amount: number | null;
  dose_unit: string | null;
  dose_text: string | null;
  reason: string | null;
  effective_date: string;
  client_entry_id: string;
}

/** MedicationChangeOut — one appended entry's outcome. `skipped` is true on an idempotent
 *  retry (client_entry_id already on file), so no new row was written. */
export interface MedicationChangeOut {
  medication_id: string;
  change_type: MedicationChangeType;
  effective_at: string;
  skipped: boolean;
}

/** MedicationChangeEntry — one entry in a medication's append-only change log. */
export interface MedicationChangeEntry {
  change_type: MedicationChangeType;
  effective_at: string;
  dose_amount: number | null;
  dose_unit: string | null;
  dose_text: string | null;
  reason: string | null;
}

/** MedicationOut — a medication folded to its current state, plus its full change log. */
export interface MedicationOut {
  medication_id: string;
  name: string;
  kind: MedicationKind;
  status: MedicationStatus;
  current_dose_amount: number | null;
  current_dose_unit: string | null;
  current_dose_text: string | null;
  prescriber: string | null;
  started_on: string;
  last_change_at: string;
  changes: MedicationChangeEntry[];
}

/** MedicationLog — the patient's folded current medication list + per-med log, active-first. */
export interface MedicationLog {
  items: MedicationOut[];
}

// ---- event.py (ADR-0045 P2 — patient-entered between-visit events & notes) ----

/** EventType — the closed vocabulary of between-visit events (plus a plain note). */
export type EventType =
  'fall' | 'er_visit' | 'new_provider' | 'hospitalization' | 'new_supplement' | 'note';

/** EventIn — record one between-visit event or note. `type='note'` requires a non-empty note.
 *  The `client_entry_id` idempotency key is minted by the endpoint client, not the caller. */
export interface EventIn {
  type: EventType;
  effective_date: string;
  note: string | null;
  client_entry_id: string;
}

/** EventOut — one recorded event. `skipped` is true on an idempotent retry. */
export interface EventOut {
  event_id: string;
  type: EventType;
  effective_at: string;
  note: string | null;
  reviewed: boolean;
  skipped: boolean;
}

/** EventList — the patient's between-visit events & notes, newest-first. */
export interface EventList {
  items: EventOut[];
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

// ---- wearable.py (ADR-0035 Phase 1) ----

/** The closed set of health-bridge metrics — kept in lockstep with the backend catalog.
 *  The `wearable_*` codes are mobility (ADR-0035); `blood_glucose` is CGM (ADR-0038), sent
 *  in canonical mg/dL (the native seam converts mmol/L at the edge). */
export type WearableMetric =
  | 'wearable_walking_speed'
  | 'wearable_step_length'
  | 'wearable_steps'
  | 'wearable_walking_distance'
  | 'wearable_walking_asymmetry'
  | 'wearable_double_support'
  | 'wearable_walking_steadiness'
  | 'blood_glucose';

export type HealthPlatform = 'apple_health' | 'health_connect';

export type WearableSourceDevice =
  'iphone' | 'apple_watch' | 'android_phone' | 'wear_os' | 'unknown';

/** WearableSampleIn — the client sends metric + value; the server derives the unit. */
export interface WearableSampleIn {
  metric: WearableMetric;
  value: number;
  effective_start: string;
  effective_end: string;
  platform: HealthPlatform;
  source_device: WearableSourceDevice;
  phone_derived: boolean;
  external_id: string | null;
}

/** WearableImportOut */
export interface WearableImportOut {
  imported: number;
  skipped: number;
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
  /** Also request clinical-note (DocumentReference) read on the EHR consent screen
   *  (ADR-0045 P2 #27). Off by default — a labs-only connect never asks for it. */
  connect_notes?: boolean;
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

/** PullNotesOut — the clinical-note pull result, COUNTS ONLY (ADR-0045 P2 #27).
 *  No note text ever leaves the backend; the handout renders metadata + an "open" affordance. */
export interface EmrPullNotesOut {
  imported: number;
  skipped: number;
  fetched: number;
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

/** ExportCaregiverLink — one caregiver-sharing link (ADR-0047), METADATA ONLY: who the
 *  patient shares with, scope, and lifecycle timestamps. No invite codes or hashes exist
 *  in this shape to leak (structural absence, like the token-free EMR connection). */
export interface ExportCaregiverLink {
  id: string;
  caregiver_display_name: string;
  scope: string;
  status: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
}

/** ExportCaregiverAlert — one caregiver alert (ADR-0047 B1), METADATA ONLY: which
 *  caregiver, which type, when raised, and whether acknowledged. No value, code label,
 *  or note text exists here to leak (structural absence, like the body-free note). */
export interface ExportCaregiverAlert {
  id: string;
  caregiver_display_name: string;
  alert_type: string;
  created_at: string | null;
  acknowledged_at: string | null;
}

/** ExportCaregiverAlertPreference — one per-type opt-in flag, the patient's own setting. */
export interface ExportCaregiverAlertPreference {
  alert_type: string;
  enabled: boolean;
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
  /** Caregiver-sharing metadata (ADR-0047, export schema 1.1) — never codes. */
  caregiver_links: ExportCaregiverLink[];
  /** Caregiver alerts + the patient's per-type opt-in state (ADR-0047 B1, export schema
   *  1.2) — metadata only. Defaulted server-side, so an older envelope may omit them. */
  caregiver_alerts?: ExportCaregiverAlert[];
  caregiver_alert_preferences?: ExportCaregiverAlertPreference[];
}

// ---- caregiver.py (ADR-0047 — Caregiver Companion Phase A) ----

/** CaregiverScope — what the PATIENT lets this caregiver see: the wellness trend only,
 *  or the full read surfaces (trend + the Visit-Ready Summary). */
export type CaregiverScope = 'trends' | 'full';

/** CaregiverLinkStatus — the link lifecycle. Nothing is visible until the patient
 *  explicitly accepts (double opt-in); a revoked link stops access instantly. */
export type CaregiverLinkStatus = 'pending' | 'active' | 'revoked';

/** CaregiverRegisterIn — caregiver self-registration exists ONLY inside the
 *  invite-claim flow: a valid code is required to create the account. */
export interface CaregiverRegisterIn {
  code: string;
  email: string;
  password: string;
  display_name: string;
}

/** InviteCreateOut — the ONE-TIME answer to creating an invite: the plaintext code
 *  appears here and never again (only its hash is stored server-side). */
export interface CaregiverInviteCreateOut {
  id: string;
  code: string;
  expires_at: string;
}

/** InviteOut — an open invite as the patient lists it; the code is unrecoverable. */
export interface CaregiverInviteOut {
  id: string;
  created_at: string;
  expires_at: string;
}

/** ClaimOut — one fixed sentence for EVERY outcome (non-enumeration: the response
 *  never reveals whether the code matched an invite). */
export interface CaregiverClaimOut {
  detail: string;
}

/** PatientLinkOut — one caregiver link as the PATIENT sees it: who, scope, lifecycle. */
export interface PatientCaregiverLinkOut {
  id: string;
  caregiver_display_name: string;
  scope: string;
  status: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

/** CaregiverPatientOut — one shared patient as the CAREGIVER sees it: display name +
 *  scope only (accepted, non-revoked links; the server's single access predicate). */
export interface CaregiverPatientOut {
  patient_id: string;
  display_name: string;
  link_id: string;
  scope: string;
  accepted_at: string;
}

/** CaregiverPatientsOut — the caregiver's shared patients. The non-urgent framing
 *  rides WITH the data (`emergency_notice`), co-located, never implied (ADR-0047). */
export interface CaregiverPatientsOut {
  patients: CaregiverPatientOut[];
  emergency_notice: string;
}

// ---- caregiver_alert.py (ADR-0047 Phase B1 — compute-on-read alerts + feed) ----

/** CaregiverAlertType — the closed set of alert kinds. `missed_checkin`/`trend_shift`
 *  are visible at either scope; `med_change`/`new_chart_note` are FULL-scope only. */
export type CaregiverAlertType = 'missed_checkin' | 'med_change' | 'trend_shift' | 'new_chart_note';

/** CaregiverAlertOut — one alert as the CAREGIVER sees it: fixed template copy + refs +
 *  the patient's display name (already on the Phase A list). NEVER a value, code label,
 *  or note text — PHI-minimal by construction. `title`/`body` are non-diagnostic template
 *  constants; the 911 framing rides `body` and the feed envelope. */
export interface CaregiverAlertOut {
  id: string;
  alert_type: CaregiverAlertType;
  patient_id: string;
  patient_display_name: string;
  title: string;
  body: string;
  created_at: string;
  acknowledged_at: string | null;
}

/** CaregiverAlertsOut — the caregiver's in-app alert feed. The non-urgent framing rides
 *  WITH the data (`emergency_notice`), co-located, exactly as Phase A does. */
export interface CaregiverAlertsOut {
  alerts: CaregiverAlertOut[];
  emergency_notice: string;
}

/** AlertPreferenceOut — one per-type opt-in flag as the PATIENT sees it (DEFAULT OFF). */
export interface AlertPreferenceOut {
  alert_type: CaregiverAlertType;
  enabled: boolean;
}

/** AlertPreferencesOut — every type is listed; a never-touched type reads DEFAULT OFF. */
export interface AlertPreferencesOut {
  preferences: AlertPreferenceOut[];
}

/** AlertPreferenceIn — turn a caregiver-alert type on or off (the type rides in the path). */
export interface AlertPreferenceIn {
  enabled: boolean;
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
