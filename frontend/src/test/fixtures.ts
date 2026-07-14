/**
 * Synthetic test data ONLY (CLAUDE.md §5) — no real patient data, ever.
 * Credentials are uppercase test constants, not secrets.
 */

import type {
  CapabilityStateOut,
  ConnectionOut,
  MeOut,
  ObservationItem,
  PanelOut,
  Trajectory,
} from '../api/types';

export const TEST_ACCESS_TOKEN = 'synthetic-access-token';
export const TEST_REFRESHED_ACCESS_TOKEN = 'synthetic-access-token-2';
export const TEST_REFRESH_TOKEN = 'synthetic-refresh-token';
export const TEST_EMAIL = 'pat.example@example.com';
export const TEST_PASSWORD = 'synthetic-test-passphrase';

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
    code: 'biomech_sway_velocity',
    display: 'Sway velocity',
    value: 11.4,
    value_text: null,
    unit: 'mm/s',
    effective_at: '2026-07-02T10:00:00Z',
    source: 'biomech',
    status: 'final',
  },
  {
    code: 'biomech_sway_velocity',
    display: 'Sway velocity',
    value: 12.9,
    value_text: null,
    unit: 'mm/s',
    effective_at: '2026-06-04T10:00:00Z',
    source: 'biomech',
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
];

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
