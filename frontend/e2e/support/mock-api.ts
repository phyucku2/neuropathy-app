/**
 * In-browser API mocks for the E2E suite.
 *
 * The built SPA talks to the API over `fetch`; there is no live backend here, so
 * every API call is intercepted with Playwright's `page.route` and fulfilled from
 * fixtures that MIRROR `src/test/fixtures.ts` + `src/test/server.ts` (the msw
 * contract the unit suite already trusts). Keeping the shapes identical means the
 * browser exercises the SAME response bodies the real API would return, so a render
 * that passes here would pass against the backend.
 *
 * Synthetic data ONLY (CLAUDE.md §5). Credential-shaped values are uppercase
 * SYNTHETIC_ constants, never real secrets (docs/lessons.md).
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Page, Route } from '@playwright/test';
import type {
  CaregiverAlertOut,
  CaregiverAlertType,
  CapabilityStateOut,
  CaregiverPatientOut,
  ConnectionOut,
  EmrConnectionOut,
  EmrProviderOut,
  EmrPullOut,
  EventList,
  EventOut,
  ExportObservation,
  ExportOut,
  LeadSection,
  MedicationLog,
  MedicationOut,
  MeOut,
  ObservationItem,
  PanelOut,
  PatientCaregiverLinkOut,
  PlaceholderRow,
  Trajectory,
  VisitSummary,
} from '../../src/api/types';

// ---- synthetic credentials + tokens (mirror src/test/fixtures.ts) ----

export const SYNTHETIC_EMAIL = 'pat.example@example.com';
export const SYNTHETIC_PASSWORD = 'synthetic-test-passphrase';

/** The real backend's DELETE /auth/me wrong-password detail (ADR-0027), verbatim. */
export const DELETE_WRONG_PASSWORD_DETAIL = "That password didn't match. Nothing was deleted.";
const SYNTHETIC_ACCESS_TOKEN = 'synthetic-access-token';
const SYNTHETIC_REFRESHED_ACCESS_TOKEN = 'synthetic-access-token-2';
export const SYNTHETIC_REFRESH_TOKEN = 'synthetic-refresh-token';

/** sessionStorage key the token store uses (src/auth/tokenStore.ts). */
export const REFRESH_TOKEN_KEY = 'neuropathy.refresh_token';

// ---- MFA / TOTP step-up for clinician+ops accounts (§1B C6) ----

export const SYNTHETIC_MFA_CODE = '123456';
export const SYNTHETIC_MFA_SECRET = 'SYNTHETICSECRETBASE32AAA';
export const SYNTHETIC_OTPAUTH_URI =
  `otpauth://totp/Neuropathy:dr.rivera%40example.com?secret=${SYNTHETIC_MFA_SECRET}` +
  '&issuer=Neuropathy&algorithm=SHA1&digits=6&period=30';
const SYNTHETIC_MFA_PENDING_TOKEN = 'synthetic-mfa-pending-token';

function isAuthorized(route: Route): boolean {
  const header = route.request().headers()['authorization'];
  return (
    header === `Bearer ${SYNTHETIC_ACCESS_TOKEN}` ||
    header === `Bearer ${SYNTHETIC_REFRESHED_ACCESS_TOKEN}`
  );
}

// ---- patient fixtures ----

export const ME: MeOut = {
  user_id: '11111111-1111-4111-8111-111111111111',
  email: SYNTHETIC_EMAIL,
  display_name: 'Pat Example',
  role: 'patient',
  patient_id: '22222222-2222-4222-8222-222222222222',
};

export const CLINICIAN_ME: MeOut = {
  user_id: '99999999-9999-4999-8999-999999999999',
  email: 'dr.rivera@example.com',
  display_name: 'Dr. Rivera',
  role: 'clinician',
  patient_id: null,
};

export const TRAJECTORY_IMPROVING: Trajectory = {
  direction: 'improving',
  confidence: 0.72,
  summary: 'Balance and daily function are up. One lab is worth a look.',
  signals: [
    // Symptom domain (ADR-0034 Phase 1 capture) — makes the composite a full 3-domain
    // score so the demo/E2E card shows Symptoms + Function + Physiologic together.
    {
      code: 'symptom_pain',
      source: 'adl',
      direction: 'improving',
      detail: 'nerve pain easing over 30 days',
    },
    {
      code: 'symptom_numbness',
      source: 'adl',
      direction: 'stable',
      detail: 'numbness or tingling steady this month',
    },
    {
      code: 'biomech_balance_score',
      source: 'biomech',
      direction: 'improving',
      detail: 'balance up 8 over 30 days',
    },
    {
      code: 'adl_daily_score',
      source: 'adl',
      direction: 'stable',
      detail: 'daily function steady this month',
    },
    {
      code: '4548-4',
      source: 'lab',
      direction: 'declining',
      detail: 'long-term blood sugar slightly up',
    },
  ],
  data_gaps: ['No lab results in the last 90 days'],
  narrative_source: 'deterministic',
  // Neuropathy Status Index (ADR-0034): a full three-domain composite, improving.
  score: 74,
  score_delta_30d: 7,
  as_of: '2026-07-12',
  confidence_level: 'high',
  data_is_stale: false,
};

export const TRAJECTORY_DECLINING: Trajectory = {
  direction: 'declining',
  confidence: 0.55,
  summary: 'Balance has slipped this month. Worth a closer look with your care team.',
  signals: [
    {
      code: 'biomech_balance_score',
      source: 'biomech',
      direction: 'declining',
      detail: 'balance down 6 over 30 days',
    },
    {
      // An insufficient_data signal MUST render the "not enough data" state,
      // never a fabricated "stable" (ADR-0015 signal honesty).
      code: 'adl_daily_score',
      source: 'adl',
      direction: 'insufficient_data',
      detail: 'not enough check-ins yet to judge',
    },
  ],
  data_gaps: ['Fewer than 3 check-ins this month'],
  narrative_source: 'deterministic',
  // NSI declining: lower score, a negative 30-day delta.
  score: 61,
  score_delta_30d: -6,
  as_of: '2026-07-11',
  confidence_level: 'medium',
  data_is_stale: false,
};

export const TRAJECTORY_INSUFFICIENT: Trajectory = {
  direction: 'insufficient_data',
  confidence: 0.1,
  summary: 'There is not enough data yet to judge a trend.',
  signals: [],
  data_gaps: ['No BioMech reports yet', 'No daily check-ins yet'],
  narrative_source: 'deterministic',
  // No domain present yet — the NSI is null (the "not enough data" card).
  score: null,
  score_delta_30d: null,
  as_of: null,
  confidence_level: null,
  data_is_stale: false,
};

/** Default observations (mirror src/test/fixtures.ts): balance (3 numeric points,
 *  higher-is-better) drives a "better" delta; HbA1c has a single reading, so
 *  selecting it shows the <2-point empty state. */
export const OBSERVATIONS: ObservationItem[] = [
  obs('biomech_balance_score', 'Balance score', 65, '{score}', '2026-07-02T10:00:00Z', 'biomech'),
  obs('biomech_balance_score', 'Balance score', 64, '{score}', '2026-06-04T10:00:00Z', 'biomech'),
  obs('biomech_balance_score', 'Balance score', 57, '{score}', '2026-05-06T10:00:00Z', 'biomech'),
  obs('biomech_gait_score', 'Gait score', 72, '{score}', '2026-07-02T10:00:00Z', 'biomech'),
  obs('biomech_gait_score', 'Gait score', 66, '{score}', '2026-06-04T10:00:00Z', 'biomech'),
  obs(
    'wearable_walking_asymmetry',
    'Walking asymmetry',
    6.1,
    '%',
    '2026-07-02T10:00:00Z',
    'wearable',
  ),
  obs(
    'wearable_walking_asymmetry',
    'Walking asymmetry',
    7.6,
    '%',
    '2026-06-04T10:00:00Z',
    'wearable',
  ),
  obs('4548-4', 'Hemoglobin A1c', 7.2, '%', '2026-06-20T09:00:00Z', 'lab'),
  // EMR-sourced records (source='emr', ADR-0008/0028) — the raw labs pulled from the
  // patient's health record, so the read-only "Your records" surface shows real content
  // in the hosted demo. Dated before the newest BioMech reading (Trends default unchanged);
  // distinct codes from 4548-4 so no trend series merges across sources.
  obs('2345-7', 'Glucose', 101, 'mg/dL', '2026-06-15T08:30:00Z', 'emr'),
  obs('2132-9', 'Vitamin B12', 420, 'pg/mL', '2026-06-15T08:30:00Z', 'emr'),
];

/** Trends showcase: exercises "better", "worse", "unit changed", and the
 *  single-reading empty state in one payload. */
export const OBSERVATIONS_TRENDS: ObservationItem[] = [
  // higher-is-better, rising → "better"
  obs('biomech_balance_score', 'Balance score', 60, '{score}', '2026-05-01T10:00:00Z', 'biomech'),
  obs('biomech_balance_score', 'Balance score', 68, '{score}', '2026-06-01T10:00:00Z', 'biomech'),
  // lower-is-better, rising → "worse"
  obs(
    'wearable_walking_asymmetry',
    'Walking asymmetry',
    5,
    '%',
    '2026-05-02T10:00:00Z',
    'wearable',
  ),
  obs(
    'wearable_walking_asymmetry',
    'Walking asymmetry',
    9,
    '%',
    '2026-06-02T10:00:00Z',
    'wearable',
  ),
  // two readings with DIFFERENT unit strings → "unit changed", no delta
  obs('hba1c', 'Hemoglobin A1c', 7, '%', '2026-05-03T09:00:00Z', 'lab'),
  obs('hba1c', 'Hemoglobin A1c', 53, 'mmol/mol', '2026-06-03T09:00:00Z', 'lab'),
  // single reading → chart empty state ("not enough readings")
  obs('biomech_cadence', 'Cadence', 104, 'steps/min', '2026-06-04T10:00:00Z', 'biomech'),
];

export const CAPABILITIES: CapabilityStateOut[] = [
  cap('ingest_biomech', 'BioMech report upload', true, 'patient', true),
  cap('ingest_labs', 'Lab result upload', true, 'patient', true),
  cap('ingest_adl', 'Daily function check-in', false, 'patient', true),
  // Opt-in symptom capture (ADR-0034 Phase 1) — default OFF.
  cap('ingest_symptoms', 'Symptom check-in (pain & numbness)', false, 'patient', true),
  cap('emr_connect', 'Medical record connection', true, 'patient', true),
];

/** Capabilities with the symptom-capture toggle ON — for the symptom check-in E2E. */
export const CAPABILITIES_SYMPTOMS_ON: CapabilityStateOut[] = CAPABILITIES.map((c) =>
  c.key === 'ingest_symptoms' ? { ...c, active: true } : c,
);

/** Adds one enforced=false ("coming soon") row to prove the read-only rendering. */
export const CAPABILITIES_WITH_UNWIRED: CapabilityStateOut[] = [
  ...CAPABILITIES,
  cap('future_source', 'Wearable step count', false, 'patient', false),
];

export const CONNECTION_PENDING: ConnectionOut = {
  id: '33333333-3333-4333-8333-333333333333',
  clinic_id: '44444444-4444-4444-8444-444444444444',
  clinic_name: 'Advanced Health & Wellness',
  status: 'pending',
  initiated_by: 'clinic',
  consent_granted_at: null,
  revoked_at: null,
};

export const CONNECTION_ACTIVE: ConnectionOut = {
  ...CONNECTION_PENDING,
  id: '55555555-5555-4555-8555-555555555555',
  clinic_name: 'Regional Medical Center',
  status: 'active',
  consent_granted_at: '2026-06-01T12:00:00Z',
};

// ---- EMR connect fixtures (ADR-0028; shapes mirror backend/app/schemas/emr.py) ----

export const EMR_STATE = 'synthetic-emr-state';
export const EMR_AUTH_CODE = 'synthetic-emr-auth-code';
export const EMR_CONNECTION_ID = '66666666-6666-4666-8666-666666666666';

/** Mirrors the real registry (backend/app/emr/providers.py): one entry with a public
 * sandbox (connectable) and one without (renders "Not available yet"). */
export const EMR_PROVIDERS: EmrProviderOut[] = [
  {
    key: 'epic',
    name: 'Epic (MyChart)',
    vendor: 'Epic Systems',
    sandbox_fhir_base: 'https://fhir.epic.example/api/FHIR/R4',
    note: 'Largest US hospital EMR; patient portal is MyChart.',
  },
  {
    key: 'meditech',
    name: 'MEDITECH',
    vendor: 'MEDITECH',
    sandbox_fhir_base: null,
    note: 'Community-hospital EMR; sandbox access granted on registration.',
  },
];

export const EMR_CONNECTION_ACTIVE: EmrConnectionOut = {
  id: EMR_CONNECTION_ID,
  patient_id: '22222222-2222-4222-8222-222222222222',
  fhir_base: 'https://fhir.epic.example/api/FHIR/R4',
  provider_name: 'Epic (MyChart)',
  status: 'active',
  granted_scope: 'launch/patient patient/Observation.read offline_access',
  patient_fhir_id: 'synthetic-fhir-patient-9',
  token_expires_at: '2026-07-13T13:00:00Z',
  revoked_at: null,
};

export const EMR_PULL: EmrPullOut = {
  imported: 2,
  results: [
    emrLab('4548-4', 'Hemoglobin A1c', 7.2, '%'),
    emrLab('2345-7', 'Glucose', 101, 'mg/dL'),
  ],
};

// ---- Visit-Ready Summary (ADR-0045) — mirrors src/test/fixtures.ts + backend schema ----

const VISIT_SUMMARY_PLACEHOLDERS: PlaceholderRow[] = [
  // emr_notes is CAPTURED now (ADR-0045 P2 #27) — a real data section, GONE from placeholders.
  { key: 'nutrition', label: 'Nutrition', status: 'not_yet_tracked', phase: 'Phase 3' },
];

/** Patient-entered medication log (ADR-0045 P2) — active supplement + stopped prescription. */
export const MEDICATIONS: MedicationLog = {
  items: [
    {
      medication_id: 'med:11111111-1111-4111-8111-aaaaaaaaaaaa',
      name: 'Alpha-lipoic acid',
      kind: 'supplement',
      status: 'active',
      current_dose_amount: 600,
      current_dose_unit: 'mg',
      current_dose_text: null,
      prescriber: 'Dr. Rivera',
      started_on: '2026-03-01',
      last_change_at: '2026-06-10T00:00:00Z',
      changes: [
        {
          change_type: 'added',
          effective_at: '2026-03-01T00:00:00Z',
          dose_amount: 300,
          dose_unit: 'mg',
          dose_text: null,
          reason: null,
        },
        {
          change_type: 'dose_changed',
          effective_at: '2026-06-10T00:00:00Z',
          dose_amount: 600,
          dose_unit: 'mg',
          dose_text: null,
          reason: 'Tolerating it well',
        },
      ],
    },
    {
      medication_id: 'med:22222222-2222-4222-8222-bbbbbbbbbbbb',
      name: 'Gabapentin',
      kind: 'prescription',
      status: 'stopped',
      current_dose_amount: 300,
      current_dose_unit: 'mg',
      current_dose_text: null,
      prescriber: 'Dr. Rivera',
      started_on: '2026-02-01',
      last_change_at: '2026-05-20T00:00:00Z',
      changes: [
        {
          change_type: 'added',
          effective_at: '2026-02-01T00:00:00Z',
          dose_amount: 300,
          dose_unit: 'mg',
          dose_text: null,
          reason: null,
        },
        {
          change_type: 'stopped',
          effective_at: '2026-05-20T00:00:00Z',
          dose_amount: null,
          dose_unit: null,
          dose_text: null,
          reason: 'Side effects',
        },
      ],
    },
  ],
};

/** Patient-entered between-visit events (ADR-0045 P2), newest-first. */
export const EVENTS: EventList = {
  items: [
    {
      event_id: 'aaaaaaaa-0000-4000-8000-000000000001',
      type: 'fall',
      effective_at: '2026-07-05T00:00:00Z',
      note: 'Lost my balance stepping off the curb, no injury.',
      reviewed: false,
      skipped: false,
    },
    {
      event_id: 'aaaaaaaa-0000-4000-8000-000000000002',
      type: 'note',
      effective_at: '2026-06-28T00:00:00Z',
      note: 'Feet feel colder in the mornings this week.',
      reviewed: false,
      skipped: false,
    },
  ],
};

export const VISIT_SUMMARY: VisitSummary = {
  generated_at: '2026-07-15T10:00:00Z',
  schema_version: '1.2',
  subject_id: '22222222-2222-4222-8222-222222222222',
  window_days: 60,
  window_end: '2026-07-15T10:00:00Z',
  current_window_start: '2026-05-16T10:00:00Z',
  prior_window_start: '2026-03-17T10:00:00Z',
  lead_section: 'what_changed',
  status: TRAJECTORY_IMPROVING,
  what_changed: {
    new_labs: [
      {
        code: '4548-4',
        label: 'Long-term blood sugar',
        source: 'lab',
        origin: 'ehr_imported',
        unit: '%',
        latest_value: 7.2,
        latest_at: '2026-06-20T09:00:00Z',
        prior_value: 6.9,
        prior_at: '2026-03-30T09:00:00Z',
        prior_unit: '%',
        delta: 0.3,
        unit_changed: false,
      },
    ],
    symptom_trend: [
      {
        code: 'symptom_pain',
        label: 'nerve pain',
        source: 'adl',
        origin: 'patient_reported',
        current_direction: 'improving',
        prior_direction: 'stable',
        changed: true,
      },
    ],
    adherence: {
      last_checkin_at: '2026-07-12T08:00:00Z',
      days_since_last_checkin: 3,
      checkins_in_window: 20,
      checkins_in_prior_window: 18,
    },
    latest_biomech: [
      {
        code: 'biomech_balance_score',
        label: 'Balance score',
        source: 'biomech',
        origin: 'document_imported',
        latest_value: 65,
        latest_at: '2026-07-02T10:00:00Z',
        prior_value: 57,
        prior_at: '2026-05-06T10:00:00Z',
        direction: 'improving',
      },
    ],
    medication_changes: [
      {
        medication_id: 'med:11111111-1111-4111-8111-aaaaaaaaaaaa',
        name: 'Alpha-lipoic acid',
        kind: 'supplement',
        change_type: 'dose_changed',
        dose_amount: 600,
        dose_unit: 'mg',
        dose_text: null,
        effective_at: '2026-06-10T00:00:00Z',
        provenance: 'patient-entered',
      },
    ],
  },
  symptoms: [
    {
      code: 'symptom_pain',
      label: 'nerve pain',
      source: 'adl',
      origin: 'patient_reported',
      points: [
        { at: '2026-05-20T08:00:00Z', value: 6 },
        { at: '2026-06-10T08:00:00Z', value: 5 },
        { at: '2026-07-12T08:00:00Z', value: 4 },
      ],
      start_value: 6,
      start_at: '2026-05-20T08:00:00Z',
      latest_value: 4,
      latest_at: '2026-07-12T08:00:00Z',
      direction: 'improving',
    },
  ],
  function: [
    {
      code: 'adl_walking',
      label: 'Walking',
      source: 'adl',
      origin: 'patient_reported',
      points: [
        { at: '2026-05-20T08:00:00Z', value: 6 },
        { at: '2026-07-12T08:00:00Z', value: 8 },
      ],
      start_value: 6,
      start_at: '2026-05-20T08:00:00Z',
      latest_value: 8,
      latest_at: '2026-07-12T08:00:00Z',
      direction: 'improving',
    },
  ],
  balance_gait: [
    {
      code: 'biomech_balance_score',
      label: 'Balance score',
      source: 'biomech',
      origin: 'document_imported',
      latest_value: 65,
      latest_at: '2026-07-02T10:00:00Z',
      prior_value: 57,
      prior_at: '2026-05-06T10:00:00Z',
      direction: 'improving',
    },
  ],
  labs: [
    {
      code: '4548-4',
      label: 'Long-term blood sugar',
      source: 'lab',
      origin: 'ehr_imported',
      unit: '%',
      latest_value: 7.2,
      latest_at: '2026-06-20T09:00:00Z',
      prior_value: 6.9,
      prior_at: '2026-03-30T09:00:00Z',
      prior_unit: '%',
      delta: 0.3,
      unit_changed: false,
    },
  ],
  activity: [
    {
      code: 'wearable_walking_asymmetry',
      label: 'Walking asymmetry',
      source: 'wearable',
      origin: 'device_stream',
      count: 24,
      mean: 6.8,
      min: 6.1,
      max: 7.6,
      latest_at: '2026-07-02T10:00:00Z',
    },
  ],
  medications: [
    {
      medication_id: 'med:11111111-1111-4111-8111-aaaaaaaaaaaa',
      name: 'Alpha-lipoic acid',
      kind: 'supplement',
      status: 'active',
      current_dose_amount: 600,
      current_dose_unit: 'mg',
      current_dose_text: null,
      prescriber: 'Dr. Rivera',
      started_on: '2026-03-01',
      last_change_at: '2026-06-10T00:00:00Z',
      provenance: 'patient-entered',
    },
    {
      medication_id: 'med:22222222-2222-4222-8222-bbbbbbbbbbbb',
      name: 'Gabapentin',
      kind: 'prescription',
      status: 'stopped',
      current_dose_amount: 300,
      current_dose_unit: 'mg',
      current_dose_text: null,
      prescriber: 'Dr. Rivera',
      started_on: '2026-02-01',
      last_change_at: '2026-05-20T00:00:00Z',
      provenance: 'patient-entered',
    },
  ],
  patient_notes: [
    {
      type: 'fall',
      display: 'Fall',
      effective_at: '2026-07-05T00:00:00Z',
      note: 'Lost my balance stepping off the curb, no injury.',
      reviewed: false,
      provenance: 'patient-entered',
    },
  ],
  emr_notes: [
    {
      type_display: 'Progress note',
      author_display: 'Dr. Rivera',
      authored_at: '2026-07-08T00:00:00Z',
      encounter_fhir_id: 'enc-8891',
      provenance: 'emr',
    },
  ],
  placeholders: VISIT_SUMMARY_PLACEHOLDERS,
  questions: {
    data_completeness: [
      'A new long-term blood sugar result was recorded in this window since the last value — review in context.',
      "A medication or supplement change was recorded in this window — confirm it's reflected in the chart.",
      'Between-visit events or notes were recorded in this window — review them with the patient.',
    ],
    change_pointed: [],
  },
  disclaimer:
    'This is a wellness summary of your own recorded data, not a diagnosis. Each item shows its ' +
    'source and date. Share it with your care team to discuss what it means.',
  sheet_label: 'current record, not a complete medical record',
};

/** Echo window_days + compute lead_section exactly like the backend (short → what_changed). */
function visitSummaryForWindow(windowDays: number): VisitSummary {
  const lead: LeadSection = windowDays <= 90 ? 'what_changed' : 'trajectory';
  return { ...VISIT_SUMMARY, window_days: windowDays, lead_section: lead };
}

// ---- caregiver fixtures (ADR-0047; mirror backend/app/schemas/caregiver.py) ----

export const CAREGIVER_ME: MeOut = {
  user_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  email: 'casey.example@example.com',
  display_name: 'Casey Example',
  role: 'caregiver',
  patient_id: null,
};

/** The backend's fixed sentences + co-located notice, verbatim. */
export const CAREGIVER_CLAIM_ACCEPTED_DETAIL =
  "If this code is valid, your request is now waiting for the patient's approval.";
export const CAREGIVER_CODE_INVALID_DETAIL =
  "That code didn't work. Check it, or ask for a new code.";
export const CAREGIVER_EMERGENCY_NOTICE =
  "This isn't for emergencies. If something's wrong right now, call 911.";

/**
 * The caregiver-sharing world as the mock backend holds it: the patient's open
 * invites (with their plaintext codes, which the real backend hands out exactly
 * once) and the caregiver links in every lifecycle state. Create ONE store per test
 * and pass it to BOTH the patient page's and the caregiver page's `installApiMocks`
 * to drive the real cross-role journey (invite → claim → accept → read → revoke) —
 * the same statefulness the real backend has.
 */
/** One seeded caregiver alert as the store holds it (ADR-0047 B1). The compute-on-read
 *  evaluators are simulated by seeding the events that already "happened"; the feed
 *  projection then scope-gates them exactly as the real backend does. */
export interface CaregiverAlertSeed {
  id: string;
  alert_type: CaregiverAlertType;
  created_at: string;
  acknowledged_at: string | null;
}

export interface CaregiverStore {
  invites: { id: string; code: string; created_at: string; expires_at: string }[];
  links: PatientCaregiverLinkOut[];
  /** Seeded alerts (the "already computed" events) — scope-gated on read. */
  alerts: CaregiverAlertSeed[];
  /** The patient's per-type opt-in flags (DEFAULT OFF). */
  preferences: Record<CaregiverAlertType, boolean>;
}

export function newCaregiverStore(): CaregiverStore {
  return {
    invites: [],
    links: [],
    alerts: [],
    preferences: {
      missed_checkin: false,
      med_change: false,
      trend_shift: false,
      new_chart_note: false,
    },
  };
}

/** Scope → the alert types it may ever see (mirrors backend type_allowed_for_scope). */
const ALERT_TYPES_BY_SCOPE: Record<'trends' | 'full', CaregiverAlertType[]> = {
  trends: ['missed_checkin', 'trend_shift'],
  full: ['missed_checkin', 'med_change', 'trend_shift', 'new_chart_note'],
};

/** The backend's fixed non-diagnostic template copy (services/caregiver_alert_copy.py),
 *  verbatim — each body carries the co-located 911 framing. */
const ALERT_COPY: Record<CaregiverAlertType, { title: string; body: string }> = {
  missed_checkin: {
    title: 'A check-in was missed',
    body:
      "It's been a little while since the last daily check-in. You might want to check in the " +
      `next time you talk. ${CAREGIVER_EMERGENCY_NOTICE}`,
  },
  med_change: {
    title: 'A medication update',
    body:
      "There's been an update to the medication list. You can see the details in the app when " +
      `you have a moment. ${CAREGIVER_EMERGENCY_NOTICE}`,
  },
  trend_shift: {
    title: 'A shift in the wellness trend',
    body: `The weekly wellness trend has shifted. Take a look in the app when you get a chance. ${CAREGIVER_EMERGENCY_NOTICE}`,
  },
  new_chart_note: {
    title: 'A new note from the care team',
    body:
      'A new note from the care team is now on file. You can find it in the app when you have ' +
      `a moment. ${CAREGIVER_EMERGENCY_NOTICE}`,
  },
};

/** Seed one alert of a given type into the store (helper for the alerts spec). */
export function seedCaregiverAlert(
  alertType: CaregiverAlertType,
  { acknowledged = false }: { acknowledged?: boolean } = {},
): CaregiverAlertSeed {
  return {
    id: crypto.randomUUID(),
    alert_type: alertType,
    created_at: '2026-07-20T10:00:00Z',
    acknowledged_at: acknowledged ? '2026-07-20T18:00:00Z' : null,
  };
}

/** A pending link (the caregiver claimed a code; the patient has not said yes). */
export function pendingCaregiverLink(name = 'Casey Example'): PatientCaregiverLinkOut {
  return {
    id: crypto.randomUUID(),
    caregiver_display_name: name,
    scope: 'trends',
    status: 'pending',
    accepted_at: null,
    revoked_at: null,
    created_at: '2026-07-14T09:00:00Z',
  };
}

/** An accepted link at the given scope. */
export function activeCaregiverLink(
  scope: 'trends' | 'full' = 'trends',
  name = 'Casey Example',
): PatientCaregiverLinkOut {
  return {
    ...pendingCaregiverLink(name),
    scope,
    status: 'active',
    accepted_at: '2026-07-10T12:00:00Z',
  };
}

/** The caregiver's shared-patients projection of the store: accepted links only. */
function caregiverPatientsOf(store: CaregiverStore): CaregiverPatientOut[] {
  return store.links
    .filter((link) => link.status === 'active' && link.accepted_at !== null)
    .map((link) => ({
      patient_id: ME.patient_id ?? '',
      display_name: ME.display_name,
      link_id: link.id,
      scope: link.scope,
      accepted_at: link.accepted_at ?? '',
    }));
}

/** The scope allowed across all of the caregiver's active links (widest wins — with a
 *  single shared patient there is at most one active link). `null` = no active link. */
function activeScopeOf(store: CaregiverStore): 'trends' | 'full' | null {
  const scopes = store.links
    .filter((link) => link.status === 'active' && link.accepted_at !== null)
    .map((link) => link.scope);
  if (scopes.length === 0) return null;
  return scopes.includes('full') ? 'full' : 'trends';
}

/** The caregiver's alert-feed projection: the seeded alerts scope-gated by the active
 *  link (a trends-only caregiver never sees a med/note alert — not even its existence). */
function caregiverAlertsOf(store: CaregiverStore): CaregiverAlertOut[] {
  const scope = activeScopeOf(store);
  if (scope === null) return [];
  const allowed = ALERT_TYPES_BY_SCOPE[scope];
  return store.alerts
    .filter((alert) => allowed.includes(alert.alert_type))
    .map((alert) => ({
      id: alert.id,
      alert_type: alert.alert_type,
      patient_id: ME.patient_id ?? '',
      patient_display_name: ME.display_name,
      title: ALERT_COPY[alert.alert_type].title,
      body: ALERT_COPY[alert.alert_type].body,
      created_at: alert.created_at,
      acknowledged_at: alert.acknowledged_at,
    }));
}

// ---- clinician fixtures ----

export const PANEL_PATIENT_ID = '22222222-2222-4222-8222-222222222222';

export const PANEL: PanelOut = {
  patients: [
    {
      patient_id: PANEL_PATIENT_ID,
      display_name: 'Pat Example',
      connection_id: '55555555-5555-4555-8555-555555555555',
      consent_granted_at: '2026-06-01T12:00:00Z',
    },
    {
      patient_id: '77777777-7777-4777-8777-777777777777',
      display_name: 'Jordan Marsh',
      connection_id: '88888888-8888-4888-8888-888888888888',
      consent_granted_at: '2026-05-20T09:00:00Z',
    },
  ],
};

export const PANEL_EMPTY: PanelOut = { patients: [] };

export const CLINIC_CAPABILITIES: CapabilityStateOut[] = [
  cap('ingest_biomech', 'BioMech report upload', true, 'clinic', true, '2026-08-06T23:59:59Z'),
  cap('ingest_labs', 'Lab result upload', true, 'clinic', true),
  cap('ingest_adl', 'Daily function check-in', false, 'clinic', true),
  cap('ai_narrative', 'AI trajectory summary', true, 'clinic', true),
  // Patient-held consent (ADR-0020 §3(b)): ALWAYS managed_by='patient', rendered
  // read-only in the clinician console.
  cap('share_with_clinic', 'Share data with my clinic', true, 'patient', true),
];

/** 25 synthetic clinic observations so the Observations tab pager spans pages,
 *  while still leaving a single-reading code so the trend table shows "not judged". */
export const CLINIC_OBSERVATIONS: ObservationItem[] = buildClinicObservations();

// ---- scenario + install ----

/** What the mock backend observed — specs assert against this (e.g. that a deletion
 *  actually reached the API, not just that the UI navigated away). */
export interface MockApiState {
  /** How many DELETE /auth/me requests succeeded (password matched -> 204). */
  accountDeletions: number;
  /** How many POST /emr/connections/{id}/pull requests were served. */
  emrPulls: number;
  /** How many DELETE /emr/connections/{id} revocations were served. */
  emrRevocations: number;
  /** Every POST /adl body the mock served (any status) — the offline-queue spec
   *  asserts the flushed entry REACHED the API with its true check_in_date. */
  adlPosts: unknown[];
  /** How many GET /me/export requests were served (ADR-0031). */
  dataExports: number;
}

/** The full ExportOut shape (ADR-0031) — mirrors backend/app/schemas/export.py, reusing
 *  the other fixtures so it stays in lockstep with what the real API would return. */
const EXPORT_OBSERVATIONS_OUT: ExportObservation[] = [
  {
    id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    source: 'lab',
    origin: 'ehr_imported',
    code: '4548-4',
    code_system: 'LOINC',
    value_num: 7.2,
    value_text: null,
    unit: '%',
    unit_system: 'UCUM',
    effective_at: '2026-06-20T09:00:00Z',
    recorded_at: '2026-06-20T09:05:00Z',
    status: 'final',
    revises_id: null,
    recorded_by_role: 'patient',
    quality: { human_confirmed: true },
    payload: { panel: 'metabolic' },
  },
];

export const EXPORT_OUT: ExportOut = {
  exported_at: '2026-07-15T10:00:00Z',
  // 1.2: caregiver_alerts + caregiver_alert_preferences added (ADR-0047 B1) — mirrors
  // backend EXPORT_SCHEMA_VERSION (1.1 added caregiver_links).
  schema_version: '1.2',
  subject_id: '22222222-2222-4222-8222-222222222222',
  account: {
    display_name: 'Pat Example',
    email: SYNTHETIC_EMAIL,
    role: 'patient',
    created_at: '2026-05-01T08:00:00Z',
  },
  patient: {
    patient_id: '22222222-2222-4222-8222-222222222222',
    display_name: 'Pat Example',
    connection_mode: 'self_connected',
    created_at: '2026-05-01T08:00:00Z',
  },
  observations: EXPORT_OBSERVATIONS_OUT,
  trajectory: TRAJECTORY_IMPROVING,
  capabilities: CAPABILITIES,
  clinic_connections: [CONNECTION_ACTIVE],
  emr_connections: [EMR_CONNECTION_ACTIVE],
  // Caregiver-sharing metadata (ADR-0047, export schema 1.1) — never codes.
  caregiver_links: [],
  // Caregiver alerts + per-type opt-in state (ADR-0047 B1, export schema 1.2) — metadata only.
  caregiver_alerts: [],
  caregiver_alert_preferences: [],
};

export interface Scenario {
  me?: MeOut;
  trajectory?: Trajectory;
  observations?: ObservationItem[];
  capabilities?: CapabilityStateOut[];
  connections?: ConnectionOut[];
  /** ADL POST result (defaults to a fresh, non-superseded check-in). */
  adl?: { status?: number; body?: unknown };
  /** BioMech import result. */
  biomech?: { status?: number; body?: unknown };
  /** Override the PUT /capabilities/:key outcome (e.g. a 409 clinically-managed). */
  putCapability?: { status: number; body: unknown };
  /** Seed the medication log (ADR-0045 P2); POSTs append to it statefully. Defaults empty. */
  medications?: MedicationOut[];
  /** Seed the between-visit event list (ADR-0045 P2); POSTs prepend to it. Defaults empty. */
  events?: EventOut[];
  // clinician surface
  panel?: PanelOut;
  clinicTrajectory?: Trajectory;
  clinicObservations?: ObservationItem[];
  clinicCapabilities?: CapabilityStateOut[];
  /** MFA factor state (§1B C6). enrolled=true makes a clinician/ops login answer the
   *  TOTP step-up; enrollment via the settings card flips it statefully. Default false. */
  mfa?: { enrolled?: boolean };
  /** Caregiver-sharing state (ADR-0047). Pass the SAME store to a patient page and a
   *  caregiver page to drive the cross-role invite → claim → accept → revoke journey;
   *  defaults to a fresh empty store. */
  caregiverStore?: CaregiverStore;
}

const CLINICALLY_MANAGED_409 = {
  detail: 'Your clinic manages this source right now, so it can’t be changed here.',
};

const FEATURE_OFF_409 = {
  detail: 'This check-in is turned off right now.',
};

const JSON_HEADERS = { 'content-type': 'application/json' };

async function fulfillJson(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, headers: JSON_HEADERS, body: JSON.stringify(body) });
}

const unauthorized = (route: Route) => fulfillJson(route, 401, { detail: 'Not authenticated' });
const patientNotFound = (route: Route) => fulfillJson(route, 404, { detail: 'Patient not found' });

/**
 * Install the full API mock on a page. Only the app's own API path prefixes are
 * intercepted; the HTML/JS/CSS/font requests fall through to the real preview
 * build (so we test the REAL production bundle). `/favicon.ico` is fulfilled 204
 * so it never logs a benign 404 to the console.
 */
export async function installApiMocks(page: Page, scenario: Scenario = {}): Promise<MockApiState> {
  const state: MockApiState = {
    accountDeletions: 0,
    emrPulls: 0,
    emrRevocations: 0,
    adlPosts: [],
    dataExports: 0,
  };
  const me = scenario.me ?? ME;
  const trajectory = scenario.trajectory ?? TRAJECTORY_IMPROVING;
  const observations = scenario.observations ?? OBSERVATIONS;
  const capabilities = scenario.capabilities ?? CAPABILITIES;
  const connections = scenario.connections ?? [CONNECTION_PENDING, CONNECTION_ACTIVE];
  const panel = scenario.panel ?? PANEL;
  const clinicTrajectory = scenario.clinicTrajectory ?? TRAJECTORY_IMPROVING;
  const clinicObservations = scenario.clinicObservations ?? OBSERVATIONS;
  const clinicCapabilities = scenario.clinicCapabilities ?? CLINIC_CAPABILITIES;
  // Stateful patient-entered capture (ADR-0045 P2): seeded from the scenario (default empty),
  // POSTs mutate these so an added med / recorded event shows up on the next GET.
  const medications: MedicationOut[] = scenario.medications ? [...scenario.medications] : [];
  const events: EventOut[] = scenario.events ? [...scenario.events] : [];
  // MFA factor state (§1B C6): confirming enrollment flips it, so a later login answers
  // the step-up — the same statefulness the real backend has.
  let mfaEnrolled = scenario.mfa?.enrolled ?? false;
  // Caregiver-sharing state (ADR-0047): possibly SHARED with another page's install so
  // the patient's accept/revoke is immediately visible to the caregiver's reads.
  const caregiverStore = scenario.caregiverStore ?? newCaregiverStore();
  let caregiverInviteSerial = 0;

  await page.route('**/favicon.ico', (route) => route.fulfill({ status: 204, body: '' }));

  await page.route(
    // /emr shares its prefix between API paths and the SPA's /emr/callback relay
    // route, exactly like /clinic (see the document-navigation note below).
    /\/(auth|me|observations|adl|biomech|trajectory|capabilities|connections|clinic|emr|medications|events|caregiver)(\/|$|\?)/,
    async (route) => {
      const req = route.request();
      // Only intercept the app's fetch/XHR API calls. The client routes /clinic and
      // /clinic/patients/{id} share a prefix with the API path space, so a document
      // navigation to them must render the SPA, not be answered as an API call. The
      // preview server proxies these prefixes to the (absent) dev backend, so we
      // serve the REAL built dist/index.html here; its /assets/*.js + /config.js
      // still load from the real preview build.
      const resourceType = req.resourceType();
      if (resourceType === 'document') {
        return route.fulfill({
          status: 200,
          headers: { 'content-type': 'text/html; charset=utf-8' },
          body: indexHtml(),
        });
      }
      if (resourceType !== 'fetch' && resourceType !== 'xhr') {
        return route.continue();
      }
      const method = req.method();
      const path = new URL(req.url()).pathname;

      // ---- auth (anonymous endpoints) ----
      if (method === 'POST' && path === '/auth/login') {
        const body = req.postDataJSON() as { email: string; password: string };
        if (
          (body.email === SYNTHETIC_EMAIL || body.email === me.email) &&
          body.password === SYNTHETIC_PASSWORD
        ) {
          // §1B C6: an enrolled clinician/ops factor turns password success into the
          // TOTP step-up — a short-lived mfa_pending token, never access/refresh.
          // Patients always get full tokens (their flow is unchanged).
          if (mfaEnrolled && me.role !== 'patient') {
            return fulfillJson(route, 200, {
              mfa_pending_token: SYNTHETIC_MFA_PENDING_TOKEN,
              token_type: 'mfa_pending',
            });
          }
          return fulfillJson(route, 200, tokenBody());
        }
        return fulfillJson(route, 401, { detail: 'Invalid email or password' });
      }
      // The login step-up (§1B C6): anonymous — the pending token rides in the body.
      if (method === 'POST' && path === '/auth/mfa/verify') {
        const body = req.postDataJSON() as { mfa_pending_token: string; code: string };
        if (
          body.mfa_pending_token === SYNTHETIC_MFA_PENDING_TOKEN &&
          body.code === SYNTHETIC_MFA_CODE
        ) {
          return fulfillJson(route, 200, tokenBody());
        }
        return fulfillJson(route, 401, { detail: 'Invalid code' });
      }
      if (method === 'POST' && path === '/auth/register') {
        return fulfillJson(route, 201, tokenBody());
      }
      if (method === 'POST' && path === '/auth/refresh') {
        const body = req.postDataJSON() as { refresh_token: string };
        if (body.refresh_token === SYNTHETIC_REFRESH_TOKEN) {
          return fulfillJson(route, 200, {
            access_token: SYNTHETIC_REFRESHED_ACCESS_TOKEN,
            token_type: 'bearer',
          });
        }
        return fulfillJson(route, 401, { detail: 'Invalid token' });
      }
      // Caregiver registration (ADR-0047) — anonymous, and possible ONLY with a live
      // invite code. The code is single-use (consumed here) and a dead one answers the
      // real backend's fixed 404 sentence. Success creates a PENDING link (double opt-in).
      if (method === 'POST' && path === '/caregiver/register') {
        const body = req.postDataJSON() as { code: string; display_name: string };
        const invite = caregiverStore.invites.find((entry) => entry.code === body.code);
        if (invite === undefined) {
          return fulfillJson(route, 404, { detail: CAREGIVER_CODE_INVALID_DETAIL });
        }
        caregiverStore.invites = caregiverStore.invites.filter((entry) => entry !== invite);
        caregiverStore.links.push(pendingCaregiverLink(body.display_name));
        return fulfillJson(route, 201, tokenBody());
      }

      // ---- everything below requires a valid bearer ----
      if (!isAuthorized(route)) {
        return unauthorized(route);
      }

      if (method === 'GET' && path === '/auth/me') {
        return fulfillJson(route, 200, me);
      }
      // ---- MFA enrollment (§1B C6): status, the ONE-TIME secret showing, confirm ----
      if (method === 'GET' && path === '/auth/mfa') {
        return fulfillJson(route, 200, { enrolled: mfaEnrolled });
      }
      if (method === 'POST' && path === '/auth/mfa/enroll') {
        return fulfillJson(route, 201, {
          otpauth_uri: SYNTHETIC_OTPAUTH_URI,
          secret: SYNTHETIC_MFA_SECRET,
        });
      }
      if (method === 'POST' && path === '/auth/mfa/enroll/confirm') {
        const body = req.postDataJSON() as { code: string };
        if (body.code === SYNTHETIC_MFA_CODE) {
          mfaEnrolled = true;
          return fulfillJson(route, 200, { enrolled: true });
        }
        return fulfillJson(route, 401, { detail: 'Invalid code' });
      }
      // Account & data deletion (ADR-0027): 204 on the right password (recorded in
      // MockApiState), 403 with the backend's verbatim detail otherwise.
      if (method === 'DELETE' && path === '/auth/me') {
        const body = req.postDataJSON() as { password: string };
        if (body.password === SYNTHETIC_PASSWORD) {
          state.accountDeletions += 1;
          return route.fulfill({ status: 204, body: '' });
        }
        return fulfillJson(route, 403, { detail: DELETE_WRONG_PASSWORD_DETAIL });
      }
      // Data export (ADR-0031): the complete record for the signed-in patient. The
      // full ExportOut shape, so the browser exercises exactly what the real API sends.
      if (method === 'GET' && path === '/me/export') {
        state.dataExports += 1;
        return fulfillJson(route, 200, EXPORT_OUT);
      }
      // Visit-Ready Summary (ADR-0045): windowed handout, echoes window_days + lead_section.
      if (method === 'GET' && path === '/me/visit-summary') {
        const window = Number(new URL(req.url()).searchParams.get('window') ?? '60');
        return fulfillJson(route, 200, visitSummaryForWindow(window));
      }
      if (method === 'GET' && path === '/trajectory') {
        return fulfillJson(route, 200, trajectory);
      }
      if (method === 'GET' && path === '/observations') {
        return fulfillJson(route, 200, page_(observations, req.url()));
      }
      if (method === 'POST' && path === '/adl') {
        const body = req.postDataJSON() as {
          walking: number;
          stairs: number;
          balance_confidence: number;
        };
        state.adlPosts.push(body);
        // An error status (feature-off 409, etc.) returns the raw override body —
        // that IS the real error shape. A success status instead MERGES the override
        // onto the full AdlCheckInOut default, so a { status: 200, body: { superseded:
        // true } } scenario flips one field without dropping the required check_in_date
        // / daily_score — a partial 200 body would be a fiction the real API (Pydantic
        // AdlCheckInOut, all fields required) could never return.
        const adlStatus = scenario.adl?.status ?? 200;
        if (adlStatus >= 400) {
          return fulfillJson(route, adlStatus, scenario.adl?.body ?? FEATURE_OFF_409);
        }
        return fulfillJson(route, adlStatus, {
          check_in_date: '2026-07-13',
          daily_score: body.walking + body.stairs + body.balance_confidence,
          superseded: false,
          ...(typeof scenario.adl?.body === 'object' ? scenario.adl.body : {}),
        });
      }
      if (method === 'POST' && path === '/biomech/reports') {
        if (scenario.biomech?.status !== undefined) {
          return fulfillJson(route, scenario.biomech.status, scenario.biomech.body);
        }
        return fulfillJson(route, 200, {
          report_kind: 'balance',
          assessment_at: '2026-07-02T10:00:00Z',
          imported: 3,
          skipped: 0,
          warnings: [],
          ...(typeof scenario.biomech?.body === 'object' ? scenario.biomech.body : {}),
        });
      }
      // ---- medications & supplements (ADR-0045 P2) ----
      if (method === 'GET' && path === '/medications') {
        return fulfillJson(route, 200, { items: medications });
      }
      if (method === 'POST' && path === '/medications') {
        const body = req.postDataJSON() as {
          name: string;
          kind: MedicationOut['kind'];
          dose_amount: number | null;
          dose_unit: string | null;
          dose_text: string | null;
          prescriber: string | null;
          started_on: string;
        };
        const medicationId = `med:${crypto.randomUUID()}`;
        const effectiveAt = `${body.started_on}T00:00:00Z`;
        medications.push({
          medication_id: medicationId,
          name: body.name,
          kind: body.kind,
          status: 'active',
          current_dose_amount: body.dose_amount,
          current_dose_unit: body.dose_unit,
          current_dose_text: body.dose_text,
          prescriber: body.prescriber,
          started_on: body.started_on,
          last_change_at: effectiveAt,
          changes: [
            {
              change_type: 'added',
              effective_at: effectiveAt,
              dose_amount: body.dose_amount,
              dose_unit: body.dose_unit,
              dose_text: body.dose_text,
              reason: null,
            },
          ],
        });
        return fulfillJson(route, 201, {
          medication_id: medicationId,
          change_type: 'added',
          effective_at: effectiveAt,
          skipped: false,
        });
      }
      const medChangeMatch = /^\/medications\/([^/]+)\/changes$/.exec(path);
      if (method === 'POST' && medChangeMatch) {
        const medicationId = decodeURIComponent(medChangeMatch[1] ?? '');
        const med = medications.find((m) => m.medication_id === medicationId);
        if (med === undefined) {
          return fulfillJson(route, 404, { detail: 'No such medication' });
        }
        const body = req.postDataJSON() as {
          change_type: 'dose_changed' | 'stopped';
          dose_amount: number | null;
          dose_unit: string | null;
          dose_text: string | null;
          reason: string | null;
          effective_date: string;
        };
        const effectiveAt = `${body.effective_date}T00:00:00Z`;
        med.changes.push({
          change_type: body.change_type,
          effective_at: effectiveAt,
          dose_amount: body.dose_amount,
          dose_unit: body.dose_unit,
          dose_text: body.dose_text,
          reason: body.reason,
        });
        med.last_change_at = effectiveAt;
        if (body.change_type === 'stopped') {
          med.status = 'stopped';
        } else {
          med.current_dose_amount = body.dose_amount;
          med.current_dose_unit = body.dose_unit;
          med.current_dose_text = body.dose_text;
        }
        return fulfillJson(route, 201, {
          medication_id: medicationId,
          change_type: body.change_type,
          effective_at: effectiveAt,
          skipped: false,
        });
      }

      // ---- between-visit events & notes (ADR-0045 P2) ----
      if (method === 'GET' && path === '/events') {
        return fulfillJson(route, 200, { items: events });
      }
      if (method === 'POST' && path === '/events') {
        const body = req.postDataJSON() as {
          type: EventOut['type'];
          effective_date: string;
          note: string | null;
        };
        const recorded: EventOut = {
          event_id: crypto.randomUUID(),
          type: body.type,
          effective_at: `${body.effective_date}T00:00:00Z`,
          note: body.note,
          reviewed: false,
          skipped: false,
        };
        // Newest-first, mirroring the real list ordering.
        events.unshift(recorded);
        return fulfillJson(route, 201, recorded);
      }

      if (method === 'GET' && path === '/capabilities') {
        return fulfillJson(route, 200, { capabilities });
      }
      if (method === 'PUT' && /^\/capabilities\/[^/]+$/.test(path)) {
        if (scenario.putCapability !== undefined) {
          return fulfillJson(route, scenario.putCapability.status, scenario.putCapability.body);
        }
        const key = decodeURIComponent(path.split('/')[2] ?? '');
        const body = req.postDataJSON() as { active: boolean };
        const existing = capabilities.find((row) => row.key === key);
        if (existing === undefined) {
          return fulfillJson(route, 404, { detail: 'Unknown capability' });
        }
        return fulfillJson(route, 200, { ...existing, active: body.active });
      }
      if (method === 'GET' && path === '/connections') {
        return fulfillJson(route, 200, connections);
      }
      if (method === 'POST' && /^\/connections\/[^/]+\/consent$/.test(path)) {
        return fulfillJson(route, 200, {
          ...CONNECTION_PENDING,
          status: 'active',
          consent_granted_at: '2026-07-13T12:00:00Z',
        });
      }
      if (method === 'DELETE' && /^\/connections\/[^/]+$/.test(path)) {
        return route.fulfill({ status: 204, body: '' });
      }

      // ---- EMR connect (ADR-0028; mirrors backend/app/api/routes/emr.py) ----
      if (method === 'GET' && path === '/emr/providers') {
        // The real endpoint's search: case-insensitive match on key, name, or vendor.
        const q = (new URL(req.url()).searchParams.get('q') ?? '').trim().toLowerCase();
        return fulfillJson(
          route,
          200,
          EMR_PROVIDERS.filter(
            (p) =>
              q === '' ||
              p.key.toLowerCase().includes(q) ||
              p.name.toLowerCase().includes(q) ||
              p.vendor.toLowerCase().includes(q),
          ),
        );
      }
      if (method === 'POST' && path === '/emr/connect') {
        // The authorize URL points back at the app's OWN /emr/callback with the
        // code+state the real EMR would append — simulating the OAuth round trip
        // without leaving the origin (the /emr document navigation renders the SPA).
        const origin = new URL(req.url()).origin;
        return fulfillJson(route, 200, {
          connection_id: EMR_CONNECTION_ID,
          authorize_url: `${origin}/emr/callback?code=${EMR_AUTH_CODE}&state=${EMR_STATE}`,
          state: EMR_STATE,
        });
      }
      if (method === 'GET' && path === '/emr/callback') {
        const params = new URL(req.url()).searchParams;
        if (params.get('state') !== EMR_STATE || params.get('code') !== EMR_AUTH_CODE) {
          // Single-use/unknown state — the real endpoint's 404.
          return fulfillJson(route, 404, { detail: 'Unknown, expired, or already-used state' });
        }
        return fulfillJson(route, 200, EMR_CONNECTION_ACTIVE);
      }
      if (method === 'POST' && /^\/emr\/connections\/[^/]+\/pull$/.test(path)) {
        state.emrPulls += 1;
        return fulfillJson(route, 200, EMR_PULL);
      }
      if (method === 'DELETE' && /^\/emr\/connections\/[^/]+$/.test(path)) {
        state.emrRevocations += 1;
        // The real revoke returns the connection with status=revoked (200, not 204).
        return fulfillJson(route, 200, {
          ...EMR_CONNECTION_ACTIVE,
          status: 'revoked',
          granted_scope: null,
          revoked_at: '2026-07-13T14:00:00Z',
        });
      }

      // ---- clinician surface ----
      if (method === 'POST' && path === '/clinic/invitations') {
        return fulfillJson(route, 202, {
          detail: 'If this email belongs to a patient account, an invitation is now pending.',
        });
      }
      if (method === 'GET' && path === '/clinic/patients') {
        return fulfillJson(route, 200, panel);
      }
      const summaryMatch = /^\/clinic\/patients\/([^/]+)\/visit-summary$/.exec(path);
      if (method === 'GET' && summaryMatch) {
        const id = decodeURIComponent(summaryMatch[1] ?? '');
        if (id !== PANEL_PATIENT_ID) {
          return patientNotFound(route);
        }
        const window = Number(new URL(req.url()).searchParams.get('window') ?? '60');
        return fulfillJson(route, 200, visitSummaryForWindow(window));
      }
      const patientMatch =
        /^\/clinic\/patients\/([^/]+)\/(trajectory|observations|capabilities)$/.exec(path);
      if (method === 'GET' && patientMatch) {
        const id = decodeURIComponent(patientMatch[1] ?? '');
        const kind = patientMatch[2];
        if (id !== PANEL_PATIENT_ID) {
          return patientNotFound(route);
        }
        if (kind === 'trajectory') {
          return fulfillJson(route, 200, clinicTrajectory);
        }
        if (kind === 'observations') {
          return fulfillJson(route, 200, page_(clinicObservations, req.url()));
        }
        return fulfillJson(route, 200, { capabilities: clinicCapabilities });
      }
      const putCapMatch = /^\/clinic\/patients\/([^/]+)\/capabilities\/([^/]+)$/.exec(path);
      if (method === 'PUT' && putCapMatch) {
        const id = decodeURIComponent(putCapMatch[1] ?? '');
        const key = decodeURIComponent(putCapMatch[2] ?? '');
        const body = req.postDataJSON() as { active: boolean; expires_at?: string | null };
        if (!body.active && body.expires_at != null) {
          return fulfillJson(route, 422, {
            detail: [
              {
                type: 'value_error',
                loc: ['body'],
                msg: 'Value error, expires_at only applies when active=true; omit it when disabling',
              },
            ],
          });
        }
        if (id !== PANEL_PATIENT_ID) {
          return patientNotFound(route);
        }
        const existing = clinicCapabilities.find((row) => row.key === key);
        if (existing === undefined) {
          return fulfillJson(route, 404, { detail: 'Unknown capability' });
        }
        return fulfillJson(route, 200, {
          ...existing,
          active: body.active,
          expires_at: body.expires_at ?? null,
        });
      }

      // ---- caregiver companion (ADR-0047; mirrors backend/app/api/routes/caregiver.py) ----

      // Patient side: invite lifecycle. The plaintext code appears ONLY in the create
      // response (the list never carries it — the real backend stores just its hash).
      if (method === 'POST' && path === '/me/caregiver-invites') {
        caregiverInviteSerial += 1;
        const invite = {
          id: crypto.randomUUID(),
          code: `SYNT-CODE-${String(caregiverInviteSerial).padStart(4, '0')}`,
          created_at: '2026-07-15T10:00:00Z',
          expires_at: '2026-07-22T10:00:00Z',
        };
        caregiverStore.invites.push(invite);
        return fulfillJson(route, 201, {
          id: invite.id,
          code: invite.code,
          expires_at: invite.expires_at,
        });
      }
      if (method === 'GET' && path === '/me/caregiver-invites') {
        return fulfillJson(
          route,
          200,
          caregiverStore.invites.map(({ id, created_at, expires_at }) => ({
            id,
            created_at,
            expires_at,
          })),
        );
      }
      const inviteMatch = /^\/me\/caregiver-invites\/([^/]+)$/.exec(path);
      if (method === 'DELETE' && inviteMatch) {
        const id = decodeURIComponent(inviteMatch[1] ?? '');
        caregiverStore.invites = caregiverStore.invites.filter((entry) => entry.id !== id);
        return route.fulfill({ status: 204, body: '' });
      }

      // Patient side: link lifecycle (accept / decline / scope / revoke).
      if (method === 'GET' && path === '/me/caregivers') {
        return fulfillJson(route, 200, caregiverStore.links);
      }
      const linkActionMatch = /^\/me\/caregivers\/([^/]+)(?:\/(accept|decline))?$/.exec(path);
      if (linkActionMatch) {
        const id = decodeURIComponent(linkActionMatch[1] ?? '');
        const action = linkActionMatch[2];
        const link = caregiverStore.links.find((entry) => entry.id === id);
        if (link === undefined) {
          return fulfillJson(route, 404, { detail: 'Caregiver not found' });
        }
        if (method === 'POST' && action === 'accept') {
          link.status = 'active';
          link.accepted_at = '2026-07-15T12:00:00Z';
          return fulfillJson(route, 200, link);
        }
        if (method === 'POST' && action === 'decline') {
          link.status = 'revoked';
          link.revoked_at = '2026-07-15T12:00:00Z';
          return route.fulfill({ status: 204, body: '' });
        }
        if (method === 'PATCH' && action === undefined) {
          const body = req.postDataJSON() as { scope: 'trends' | 'full' };
          link.scope = body.scope;
          return fulfillJson(route, 200, link);
        }
        if (method === 'DELETE' && action === undefined) {
          // Revocation is instant, idempotent, and never blockable (ADR-0047).
          link.status = 'revoked';
          link.revoked_at = '2026-07-15T12:00:00Z';
          return route.fulfill({ status: 204, body: '' });
        }
      }

      // Caregiver side: claim + reads. The claim's 202 is byte-identical whether or
      // not the code matched (non-enumeration); a match creates a PENDING link.
      if (method === 'POST' && path === '/caregiver/claims') {
        const body = req.postDataJSON() as { code: string };
        const invite = caregiverStore.invites.find((entry) => entry.code === body.code);
        if (invite !== undefined) {
          caregiverStore.invites = caregiverStore.invites.filter((entry) => entry !== invite);
          caregiverStore.links.push(pendingCaregiverLink(me.display_name));
        }
        return fulfillJson(route, 202, { detail: CAREGIVER_CLAIM_ACCEPTED_DETAIL });
      }
      if (method === 'GET' && path === '/caregiver/patients') {
        return fulfillJson(route, 200, {
          patients: caregiverPatientsOf(caregiverStore),
          emergency_notice: CAREGIVER_EMERGENCY_NOTICE,
        });
      }
      const caregiverReadMatch =
        /^\/caregiver\/patients\/([^/]+)\/(trajectory|visit-summary)$/.exec(path);
      if (method === 'GET' && caregiverReadMatch) {
        const id = decodeURIComponent(caregiverReadMatch[1] ?? '');
        const kind = caregiverReadMatch[2];
        const shared = caregiverPatientsOf(caregiverStore).find((entry) => entry.patient_id === id);
        // 404-over-403: unknown, revoked, AND insufficient-scope are indistinguishable.
        if (shared === undefined || (kind === 'visit-summary' && shared.scope !== 'full')) {
          return patientNotFound(route);
        }
        if (kind === 'trajectory') {
          return fulfillJson(route, 200, trajectory);
        }
        const window = Number(new URL(req.url()).searchParams.get('window') ?? '60');
        return fulfillJson(route, 200, visitSummaryForWindow(window));
      }

      // Caregiver alert feed (ADR-0047 B1): compute-on-read list, scope-gated. A
      // trends-only caregiver never sees a med/note alert — not even its existence.
      if (method === 'GET' && path === '/caregiver/alerts') {
        return fulfillJson(route, 200, {
          alerts: caregiverAlertsOf(caregiverStore),
          emergency_notice: CAREGIVER_EMERGENCY_NOTICE,
        });
      }
      const ackMatch = /^\/caregiver\/alerts\/([^/]+)\/ack$/.exec(path);
      if (method === 'POST' && ackMatch) {
        const id = decodeURIComponent(ackMatch[1] ?? '');
        // Only a currently-readable (scope-gated) alert can be acked; anything else is
        // 404-over-403 (unknown / not-owned / out-of-scope are indistinguishable).
        const readable = caregiverAlertsOf(caregiverStore).find((alert) => alert.id === id);
        if (readable === undefined) {
          return fulfillJson(route, 404, { detail: 'Alert not found' });
        }
        const seed = caregiverStore.alerts.find((alert) => alert.id === id);
        if (seed !== undefined && seed.acknowledged_at === null) {
          seed.acknowledged_at = '2026-07-20T18:00:00Z';
        }
        return route.fulfill({ status: 204, body: '' });
      }

      // Patient side: per-type caregiver-alert opt-ins (ADR-0047 B1 — DEFAULT OFF).
      if (method === 'GET' && path === '/me/caregiver-alert-preferences') {
        return fulfillJson(route, 200, {
          preferences: (Object.keys(caregiverStore.preferences) as CaregiverAlertType[]).map(
            (alertType) => ({
              alert_type: alertType,
              enabled: caregiverStore.preferences[alertType],
            }),
          ),
        });
      }
      const prefMatch = /^\/me\/caregiver-alert-preferences\/([^/]+)$/.exec(path);
      if (method === 'PUT' && prefMatch) {
        const alertType = decodeURIComponent(prefMatch[1] ?? '') as CaregiverAlertType;
        const body = req.postDataJSON() as { enabled: boolean };
        caregiverStore.preferences[alertType] = body.enabled;
        return fulfillJson(route, 200, { alert_type: alertType, enabled: body.enabled });
      }

      // Any unmocked API path is a test bug — fail loudly rather than hang.
      return fulfillJson(route, 500, { detail: `Unmocked ${method} ${path}` });
    },
  );
  return state;
}

export { CLINICALLY_MANAGED_409, FEATURE_OFF_409 };

// ---- helpers ----

/** The real built index.html, read once (the preview build produces it). */
let cachedIndexHtml: string | null = null;
function indexHtml(): string {
  if (cachedIndexHtml === null) {
    const here = dirname(fileURLToPath(import.meta.url));
    cachedIndexHtml = readFileSync(join(here, '..', '..', 'dist', 'index.html'), 'utf8');
  }
  return cachedIndexHtml;
}

function tokenBody() {
  return {
    access_token: SYNTHETIC_ACCESS_TOKEN,
    refresh_token: SYNTHETIC_REFRESH_TOKEN,
    token_type: 'bearer',
  };
}

/** Slice an observation array into an ObservationPage honoring limit/offset. */
function page_(items: ObservationItem[], url: string) {
  const params = new URL(url).searchParams;
  const limit = Number(params.get('limit') ?? '100');
  const offset = Number(params.get('offset') ?? '0');
  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    limit,
    offset,
  };
}

function emrLab(loinc_code: string, display: string, value: number, unit: string) {
  return {
    loinc_code,
    source_record_id: `synthetic-${loinc_code}`,
    display,
    value,
    value_text: null,
    unit,
    effective_at: '2026-06-15T08:30:00Z',
    issued_at: null,
    status: 'final',
    reference_range: null,
    interpretation: null,
    code_system: 'LOINC',
    unit_system: 'UCUM',
  };
}

function obs(
  code: string,
  display: string,
  value: number,
  unit: string,
  effective_at: string,
  source: string,
): ObservationItem {
  return { code, display, value, value_text: null, unit, effective_at, source, status: 'final' };
}

function cap(
  key: string,
  name: string,
  active: boolean,
  managed_by: 'patient' | 'clinic',
  enforced: boolean,
  expires_at: string | null = null,
): CapabilityStateOut {
  return { key, name, active, managed_by, expires_at, enforced };
}

function buildClinicObservations(): ObservationItem[] {
  const items: ObservationItem[] = [];
  for (let i = 0; i < 12; i += 1) {
    const day = String(28 - i).padStart(2, '0');
    items.push(
      obs(
        'biomech_balance_score',
        'Balance score',
        60 + i,
        '{score}',
        `2026-06-${day}T10:00:00Z`,
        'biomech',
      ),
    );
  }
  for (let i = 0; i < 12; i += 1) {
    const day = String(28 - i).padStart(2, '0');
    items.push(
      obs(
        'wearable_walking_asymmetry',
        'Walking asymmetry',
        10 + i * 0.2,
        '%',
        `2026-05-${day}T10:00:00Z`,
        'wearable',
      ),
    );
  }
  // A single-reading lab so the trend table shows "not judged".
  items.push(obs('4548-4', 'Hemoglobin A1c', 7.1, '%', '2026-04-10T09:00:00Z', 'lab'));
  return items;
}
