/**
 * Signal semantics for display — a UI mirror of the backend's directionality
 * registry (backend/app/trajectory/directionality.py). A rising line is only
 * "good" when higher is actually better for that measure, so every chart states
 * its direction-of-better in plain language; unknown codes are tracked but
 * never judged (no silent clinical claims).
 */

export type Polarity = 'higher_is_better' | 'lower_is_better' | 'in_range_is_better' | 'unknown';

interface SignalMeta {
  polarity: Polarity;
  label: string;
}

const HBA1C: SignalMeta = { polarity: 'lower_is_better', label: 'Long-term blood sugar' };
const B12: SignalMeta = { polarity: 'in_range_is_better', label: 'Vitamin B12' };
const EGFR: SignalMeta = { polarity: 'higher_is_better', label: 'Kidney function' };
const GLUCOSE: SignalMeta = { polarity: 'in_range_is_better', label: 'Blood sugar' };
const TSH: SignalMeta = { polarity: 'in_range_is_better', label: 'Thyroid level' };
const FOLATE: SignalMeta = { polarity: 'in_range_is_better', label: 'Folate' };
const VITAMIN_D: SignalMeta = { polarity: 'in_range_is_better', label: 'Vitamin D' };

const REGISTRY: Record<string, SignalMeta> = {
  // Labs — LOINC codes and friendly keys point at the same entry.
  '4548-4': HBA1C,
  hba1c: HBA1C,
  '2132-9': B12,
  vitamin_b12: B12,
  b12: B12,
  '62238-1': EGFR,
  '33914-3': EGFR,
  egfr: EGFR,
  '2345-7': GLUCOSE,
  '1558-6': GLUCOSE,
  glucose: GLUCOSE,
  '3016-3': TSH,
  tsh: TSH,
  '2284-8': FOLATE,
  folate: FOLATE,
  '1989-3': VITAMIN_D,
  vitamin_d: VITAMIN_D,
  // ADL daily check-in — all scored so higher means better function.
  adl_walking: { polarity: 'higher_is_better', label: 'Walking' },
  adl_stairs: { polarity: 'higher_is_better', label: 'Stairs' },
  adl_balance_confidence: { polarity: 'higher_is_better', label: 'Balance confidence' },
  adl_daily_score: { polarity: 'higher_is_better', label: 'Daily function score' },
  // Symptom check-in (ADR-0034) — higher raw = worse, so lower is better. Distinct
  // labels from the lab-side "pain" so the self-reported symptom never renders twice.
  symptom_pain: { polarity: 'lower_is_better', label: 'nerve pain' },
  symptom_numbness: { polarity: 'lower_is_better', label: 'numbness or tingling' },
  // BioMech report metrics (ADR-0014; real report format ADR-0036). Mirrors the backend
  // directionality registry (backend/app/trajectory/directionality.py) — the two device-grade
  // composites (balance/gait score) plus their component metrics.
  biomech_balance_score: { polarity: 'higher_is_better', label: 'Balance score' },
  biomech_balance_speed_normal: { polarity: 'higher_is_better', label: 'Balance speed' },
  biomech_balance_movement_normal: { polarity: 'higher_is_better', label: 'Balance steadiness' },
  biomech_balance_position_normal: { polarity: 'higher_is_better', label: 'Balance position' },
  biomech_gait_score: { polarity: 'higher_is_better', label: 'Gait score' },
  biomech_cadence: { polarity: 'unknown', label: 'Cadence' },
  biomech_step_length: { polarity: 'higher_is_better', label: 'Step length' },
  biomech_total_steps: { polarity: 'unknown', label: 'Total steps' },
  biomech_impact_symmetry: { polarity: 'higher_is_better', label: 'Walking symmetry' },
  biomech_support_ratio: { polarity: 'higher_is_better', label: 'Support balance' },
  biomech_single_support_symmetry: {
    polarity: 'higher_is_better',
    label: 'Single-support symmetry',
  },
  biomech_pelvic_tilt_neutral: { polarity: 'higher_is_better', label: 'Pelvic alignment' },
  // Wearable / phone mobility metrics (source='wearable', ADR-0035 Phase 1). Codes match
  // schemas/wearable.py; polarity mirrors the backend registry (the verified reliability split
  // lives in the fidelity tier, not here).
  wearable_walking_speed: { polarity: 'higher_is_better', label: 'Walking speed' },
  wearable_step_length: { polarity: 'higher_is_better', label: 'Step length' },
  wearable_steps: { polarity: 'higher_is_better', label: 'Daily steps' },
  wearable_walking_distance: { polarity: 'higher_is_better', label: 'Walking distance' },
  wearable_walking_asymmetry: { polarity: 'lower_is_better', label: 'Walking asymmetry' },
  wearable_double_support: { polarity: 'lower_is_better', label: 'Double-support time' },
  wearable_walking_steadiness: { polarity: 'higher_is_better', label: 'Walking steadiness' },
};

export function polarityFor(code: string): Polarity {
  return REGISTRY[code.toLowerCase()]?.polarity ?? 'unknown';
}

/** Display name for a signal code: registry label, else a humanized code. */
export function labelFor(code: string, display?: string | null): string {
  if (display != null && display !== '') {
    return display;
  }
  const known = REGISTRY[code.toLowerCase()];
  if (known !== undefined) {
    return known.label;
  }
  const words = code.replace(/[_.]/g, ' ').trim();
  return words === '' ? code : words.charAt(0).toUpperCase() + words.slice(1);
}

/** The plain-language direction-of-better sentence shown under each chart. */
export function directionOfBetter(code: string): string {
  switch (polarityFor(code)) {
    case 'higher_is_better':
      return 'Higher is better for this measure.';
    case 'lower_is_better':
      return 'Lower is better for this measure.';
    case 'in_range_is_better':
      return 'Best when inside the normal range.';
    case 'unknown':
      return 'This measure is tracked, but a change is not judged better or worse.';
  }
}

/**
 * Judge a numeric change against the measure's polarity:
 * 'better' | 'worse' | 'neutral' — neutral for no change, in-range, and unknown.
 */
export function judgeChange(code: string, delta: number): 'better' | 'worse' | 'neutral' {
  if (delta === 0) {
    return 'neutral';
  }
  const polarity = polarityFor(code);
  if (polarity === 'higher_is_better') {
    return delta > 0 ? 'better' : 'worse';
  }
  if (polarity === 'lower_is_better') {
    return delta < 0 ? 'better' : 'worse';
  }
  return 'neutral';
}

/** Friendly name for an observation/signal source. */
export function sourceLabel(source: string): string {
  switch (source) {
    case 'biomech':
      return 'BioMech';
    case 'lab':
      return 'Lab';
    case 'adl':
      return 'Check-in';
    case 'wearable':
      return 'Phone/watch';
    case 'emr':
      return 'Your records';
    default:
      return source.charAt(0).toUpperCase() + source.slice(1);
  }
}

/** UCUM annotation units like "{score}" display without the braces. */
export function displayUnit(unit: string | null): string {
  if (unit === null) {
    return '';
  }
  return unit.replace(/[{}]/g, '');
}
