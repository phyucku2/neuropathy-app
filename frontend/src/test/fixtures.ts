/**
 * Synthetic test data ONLY (CLAUDE.md §5) — no real patient data, ever.
 * Credentials are uppercase test constants, not secrets.
 */

import type {
  CapabilityStateOut,
  ConnectionOut,
  EmrConnectionOut,
  EmrConnectStartOut,
  EmrProviderOut,
  EmrPullOut,
  EventList,
  ExportObservation,
  ExportOut,
  LeadSection,
  MedicationLog,
  MeOut,
  ObservationItem,
  PanelOut,
  PlaceholderRow,
  Trajectory,
  VisitSummary,
} from '../api/types';

export const TEST_ACCESS_TOKEN = 'synthetic-access-token';
export const TEST_REFRESHED_ACCESS_TOKEN = 'synthetic-access-token-2';
export const TEST_REFRESH_TOKEN = 'synthetic-refresh-token';
export const TEST_EMAIL = 'pat.example@example.com';
export const TEST_PASSWORD = 'synthetic-test-passphrase';

/** The real backend's DELETE /auth/me wrong-password detail (ADR-0027), verbatim. */
export const DELETE_WRONG_PASSWORD_DETAIL = "That password didn't match. Nothing was deleted.";

export const ME: MeOut = {
  user_id: '11111111-1111-4111-8111-111111111111',
  email: TEST_EMAIL,
  display_name: 'Pat Example',
  role: 'patient',
  patient_id: '22222222-2222-4222-8222-222222222222',
};

export const TRAJECTORY_IMPROVING: Trajectory = {
  direction: 'improving',
  confidence: 0.72,
  summary: 'Balance and daily function are up. One lab is worth a look.',
  signals: [
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

export const TRAJECTORY_AI: Trajectory = {
  ...TRAJECTORY_IMPROVING,
  summary: 'Your balance keeps getting steadier — nice work this month.',
  narrative_source: 'ai',
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

export const OBSERVATIONS: ObservationItem[] = [
  {
    code: 'biomech_balance_score',
    display: 'Balance score',
    value: 65,
    value_text: null,
    unit: '{score}',
    effective_at: '2026-07-02T10:00:00Z',
    source: 'biomech',
    status: 'final',
  },
  {
    code: 'biomech_balance_score',
    display: 'Balance score',
    value: 64,
    value_text: null,
    unit: '{score}',
    effective_at: '2026-06-04T10:00:00Z',
    source: 'biomech',
    status: 'final',
  },
  {
    code: 'biomech_balance_score',
    display: 'Balance score',
    value: 57,
    value_text: null,
    unit: '{score}',
    effective_at: '2026-05-06T10:00:00Z',
    source: 'biomech',
    status: 'final',
  },
  {
    code: 'biomech_gait_score',
    display: 'Gait score',
    value: 72,
    value_text: null,
    unit: '{score}',
    effective_at: '2026-07-02T10:00:00Z',
    source: 'biomech',
    status: 'final',
  },
  {
    code: 'biomech_gait_score',
    display: 'Gait score',
    value: 66,
    value_text: null,
    unit: '{score}',
    effective_at: '2026-06-04T10:00:00Z',
    source: 'biomech',
    status: 'final',
  },
  // Real-world walking asymmetry from the phone/watch health bridge (source='wearable',
  // ADR-0035) — a lower-is-better mobility metric. Easing 7.6 -> 6.1 % over the month.
  {
    code: 'wearable_walking_asymmetry',
    display: 'Walking asymmetry',
    value: 6.1,
    value_text: null,
    unit: '%',
    effective_at: '2026-07-02T10:00:00Z',
    source: 'wearable',
    status: 'final',
  },
  {
    code: 'wearable_walking_asymmetry',
    display: 'Walking asymmetry',
    value: 7.6,
    value_text: null,
    unit: '%',
    effective_at: '2026-06-04T10:00:00Z',
    source: 'wearable',
    status: 'final',
  },
  {
    code: '4548-4',
    display: 'Hemoglobin A1c',
    value: 7.2,
    value_text: null,
    unit: '%',
    effective_at: '2026-06-20T09:00:00Z',
    source: 'lab',
    status: 'final',
  },
  // EMR-sourced records (source='emr', ADR-0008/0028) — the raw labs pulled from the
  // patient's health record. These power the read-only "Your records" surface (they
  // render there with a "from your health record" provenance line, never judged). Dates
  // sit BEFORE the newest BioMech reading so Trends' default-selected metric is unchanged;
  // codes are distinct from the lab-sourced 4548-4 so no trend series merges across them.
  {
    code: '2345-7',
    display: 'Glucose',
    value: 101,
    value_text: null,
    unit: 'mg/dL',
    effective_at: '2026-06-15T08:30:00Z',
    source: 'emr',
    status: 'final',
  },
  {
    code: '2132-9',
    display: 'Vitamin B12',
    value: 420,
    value_text: null,
    unit: 'pg/mL',
    effective_at: '2026-06-15T08:30:00Z',
    source: 'emr',
    status: 'final',
  },
];

// ---- Visit-Ready Summary (ADR-0045) — mirrors backend/app/schemas/visit_summary.py ----

/** The backend's non-diagnostic note + sheet label, verbatim (ride in the envelope). */
export const VISIT_SUMMARY_DISCLAIMER =
  'This is a wellness summary of your own recorded data, not a diagnosis. Each item shows its ' +
  'source and date. Share it with your care team to discuss what it means.';
export const VISIT_SUMMARY_SHEET_LABEL = 'current record, not a complete medical record';

/** The render-only placeholder rows (ADR-0045). Medications & patient notes are CAPTURED as of
 *  P2 and dropped from here; emr_notes (Phase 2b) and nutrition (Phase 3) stay render-only. */
export const VISIT_SUMMARY_PLACEHOLDERS: PlaceholderRow[] = [
  { key: 'emr_notes', label: 'EMR clinician notes', status: 'not_yet_tracked', phase: 'Phase 2b' },
  { key: 'nutrition', label: 'Nutrition', status: 'not_yet_tracked', phase: 'Phase 3' },
];

/** Patient-entered medication log (ADR-0045 P2) — an active supplement with a dose-change plus a
 *  stopped prescription, so the folded current state + append-only history both render. */
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

/** Patient-entered between-visit events (ADR-0045 P2), newest-first: a fall with a note and a
 *  plain typed note. The note text is the patient's own words (synthetic). */
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

/** A rich default summary (window 60 → lead_section 'what_changed'). Self-consistent synthetic
 *  data; the status reuses TRAJECTORY_IMPROVING so the hero renders the full NSI card. */
export const VISIT_SUMMARY: VisitSummary = {
  generated_at: '2026-07-15T10:00:00Z',
  schema_version: '1.1',
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
      {
        code: 'symptom_numbness',
        label: 'numbness or tingling',
        source: 'adl',
        origin: 'patient_reported',
        current_direction: 'stable',
        prior_direction: 'stable',
        changed: false,
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
    // A dose change recorded inside the current window (ADR-0045 P2) — surfaces under
    // "What changed" and triggers MED_CHANGE_QUESTION on the backend.
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
    {
      code: 'symptom_numbness',
      label: 'numbness or tingling',
      source: 'adl',
      origin: 'patient_reported',
      points: [
        { at: '2026-05-20T08:00:00Z', value: 5 },
        { at: '2026-07-12T08:00:00Z', value: 5 },
      ],
      start_value: 5,
      start_at: '2026-05-20T08:00:00Z',
      latest_value: 5,
      latest_at: '2026-07-12T08:00:00Z',
      direction: 'stable',
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
    {
      // A single-reading series so the "not enough readings to draw a line" branch renders.
      code: 'adl_balance_confidence',
      label: 'Balance confidence',
      source: 'adl',
      origin: 'patient_reported',
      points: [{ at: '2026-05-20T08:00:00Z', value: 7 }],
      start_value: null,
      start_at: null,
      latest_value: 7,
      latest_at: '2026-05-20T08:00:00Z',
      direction: 'insufficient_data',
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
    {
      // No prior value → the "no prior value in the record" branch + insufficient_data direction.
      code: 'biomech_gait_score',
      label: 'Gait score',
      source: 'biomech',
      origin: 'document_imported',
      latest_value: 72,
      latest_at: '2026-07-02T10:00:00Z',
      prior_value: null,
      prior_at: null,
      direction: 'insufficient_data',
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
  // Folded current medications (ADR-0045 P2): an active supplement + a stopped prescription.
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
  // Between-visit events/notes in the window (ADR-0045 P2), newest-first.
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
  placeholders: VISIT_SUMMARY_PLACEHOLDERS,
  questions: {
    data_completeness: [
      'A new long-term blood sugar result was recorded in this window since the last value — review in context.',
      "A medication or supplement change was recorded in this window — confirm it's reflected in the chart.",
      'Between-visit events or notes were recorded in this window — review them with the patient.',
    ],
    change_pointed: [],
  },
  disclaimer: VISIT_SUMMARY_DISCLAIMER,
  sheet_label: VISIT_SUMMARY_SHEET_LABEL,
};

/** The empty-account honesty state: NSI null, every section empty, minimal questions. */
export const VISIT_SUMMARY_INSUFFICIENT: VisitSummary = {
  ...VISIT_SUMMARY,
  status: TRAJECTORY_INSUFFICIENT,
  what_changed: {
    new_labs: [],
    symptom_trend: [],
    adherence: {
      last_checkin_at: null,
      days_since_last_checkin: null,
      checkins_in_window: 0,
      checkins_in_prior_window: 0,
    },
    latest_biomech: [],
    medication_changes: [],
  },
  symptoms: [],
  function: [],
  balance_gait: [],
  labs: [],
  activity: [],
  medications: [],
  patient_notes: [],
  questions: { data_completeness: [], change_pointed: [] },
};

/** With the D2 feature flag ON: the interpretive change-pointed prompts are populated. */
export const VISIT_SUMMARY_WITH_CHANGE_QUESTIONS: VisitSummary = {
  ...VISIT_SUMMARY,
  questions: {
    data_completeness: VISIT_SUMMARY.questions.data_completeness,
    change_pointed: [
      'The nerve pain trend direction changed over the last 60 days — ask the patient about it.',
    ],
  },
};

/** The backend computes lead_section from the window (short → what_changed, 120/365 →
 *  trajectory) and echoes window_days; the mock mirrors that so the picker changes the payload. */
export function visitSummaryForWindow(windowDays: number): VisitSummary {
  const lead: LeadSection = windowDays <= 90 ? 'what_changed' : 'trajectory';
  return { ...VISIT_SUMMARY, window_days: windowDays, lead_section: lead };
}

export const CAPABILITIES: CapabilityStateOut[] = [
  {
    key: 'ingest_biomech',
    name: 'BioMech report upload',
    active: true,
    managed_by: 'patient',
    expires_at: null,
    enforced: true,
  },
  {
    key: 'ingest_labs',
    name: 'Lab result upload',
    active: true,
    managed_by: 'patient',
    expires_at: null,
    enforced: true,
  },
  {
    key: 'ingest_adl',
    name: 'Daily function check-in',
    active: false,
    managed_by: 'patient',
    expires_at: null,
    enforced: true,
  },
  {
    // Opt-in symptom capture (ADR-0034 Phase 1) — default OFF until the owner enables it.
    key: 'ingest_symptoms',
    name: 'Symptom check-in (pain & numbness)',
    active: false,
    managed_by: 'patient',
    expires_at: null,
    enforced: true,
  },
  {
    key: 'emr_connect',
    name: 'Medical record connection',
    active: true,
    managed_by: 'patient',
    expires_at: null,
    // Wired to the EMR connect flow as of ADR-0020 — interactive, not "coming soon".
    enforced: true,
  },
];

// ---- clinician surface ----

export const CLINICIAN_ME: MeOut = {
  user_id: '99999999-9999-4999-8999-999999999999',
  email: 'dr.rivera@example.com',
  display_name: 'Dr. Rivera',
  role: 'clinician',
  patient_id: null,
};

/** The consented patient the default clinic handlers serve; any other id is 404. */
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

export const CLINIC_CAPABILITIES: CapabilityStateOut[] = [
  {
    key: 'ingest_biomech',
    name: 'BioMech report upload',
    active: true,
    managed_by: 'clinic',
    expires_at: '2026-08-06T23:59:59Z',
    enforced: true,
  },
  {
    key: 'ingest_labs',
    name: 'Lab result upload',
    active: true,
    managed_by: 'clinic',
    expires_at: null,
    enforced: true,
  },
  {
    key: 'ingest_adl',
    name: 'Daily function check-in',
    active: false,
    managed_by: 'clinic',
    expires_at: null,
    enforced: true,
  },
  {
    key: 'ai_narrative',
    name: 'AI trajectory summary',
    active: true,
    managed_by: 'clinic',
    expires_at: null,
    // Wired to narrator scheduling as of ADR-0020 — interactive, not "not wired yet".
    enforced: true,
  },
  {
    key: 'share_with_clinic',
    name: 'Share data with my clinic',
    active: true,
    // Patient-held consent (ADR-0020 §3(b)): always managed_by='patient', even
    // while the patient is clinically managed. The clinician console renders it
    // read-only — a clinician write is refused 409 (PatientHeldCapabilityError).
    managed_by: 'patient',
    expires_at: null,
    enforced: true,
  },
];

// ---- EMR connect (ADR-0028; shapes mirror backend/app/schemas/emr.py) ----

/** Two registry providers: one with a public sandbox (connectable) and one without
 * (renders "Not available yet" — the API would 422 a connect for it). */
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

export const EMR_STATE = 'synthetic-emr-state';
export const EMR_AUTH_CODE = 'synthetic-emr-auth-code';
export const EMR_CONNECTION_ID = '66666666-6666-4666-8666-666666666666';

export const EMR_CONNECT_START: EmrConnectStartOut = {
  connection_id: EMR_CONNECTION_ID,
  authorize_url: `https://ehr.example/oauth/authorize?state=${EMR_STATE}`,
  state: EMR_STATE,
};

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

export const EMR_CONNECTION_REVOKED: EmrConnectionOut = {
  ...EMR_CONNECTION_ACTIVE,
  status: 'revoked',
  granted_scope: null,
  revoked_at: '2026-07-13T14:00:00Z',
};

export const EMR_PULL: EmrPullOut = {
  imported: 2,
  results: [
    {
      loinc_code: '4548-4',
      source_record_id: 'synthetic-obs-1',
      display: 'Hemoglobin A1c',
      value: 7.2,
      value_text: null,
      unit: '%',
      effective_at: '2026-06-15T08:30:00Z',
      issued_at: null,
      status: 'final',
      reference_range: null,
      interpretation: null,
      code_system: 'LOINC',
      unit_system: 'UCUM',
    },
    {
      loinc_code: '2345-7',
      source_record_id: 'synthetic-obs-2',
      display: 'Glucose',
      value: 101,
      value_text: null,
      unit: 'mg/dL',
      effective_at: '2026-06-15T08:30:00Z',
      issued_at: null,
      status: 'final',
      reference_range: null,
      interpretation: null,
      code_system: 'LOINC',
      unit_system: 'UCUM',
    },
  ],
};

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

// ---- data export (ADR-0031) — mirrors backend/app/schemas/export.py ----

/** Two observations with a comma + quote in text/unit, so the CSV flattener's escaping
 *  is exercised by real fixture data. */
export const EXPORT_OBSERVATIONS: ExportObservation[] = [
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
  {
    id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    source: 'adl',
    origin: 'patient_reported',
    code: 'adl_daily_score',
    code_system: null,
    value_num: 9,
    value_text: 'steady, "good" day',
    unit: '{score}, per day',
    unit_system: null,
    effective_at: '2026-07-01T12:00:00Z',
    recorded_at: '2026-07-01T12:00:00Z',
    status: 'final',
    revises_id: null,
    recorded_by_role: 'patient',
    quality: {},
    payload: {},
  },
];

export const EXPORT: ExportOut = {
  exported_at: '2026-07-15T10:00:00Z',
  schema_version: '1.0',
  subject_id: ME.patient_id ?? '22222222-2222-4222-8222-222222222222',
  account: {
    display_name: ME.display_name,
    email: ME.email,
    role: 'patient',
    created_at: '2026-05-01T08:00:00Z',
  },
  patient: {
    patient_id: ME.patient_id ?? '22222222-2222-4222-8222-222222222222',
    display_name: ME.display_name,
    connection_mode: 'self_connected',
    created_at: '2026-05-01T08:00:00Z',
  },
  observations: EXPORT_OBSERVATIONS,
  trajectory: TRAJECTORY_IMPROVING,
  capabilities: CAPABILITIES,
  clinic_connections: [CONNECTION_ACTIVE],
  emr_connections: [EMR_CONNECTION_ACTIVE],
};
