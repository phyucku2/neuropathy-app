/**
 * Wearable/phone health-data seam (ADR-0035 Phase 1) — the real-world ADL tier.
 *
 * Imports mobility metrics from **Apple HealthKit (iOS)** / **Android Health Connect**
 * and posts them to the backend as research-grade Observations (POST /wearable). The
 * **phone is the base**; a watch is optional.
 *
 * Native-only AND plugin-gated. There is **no health plugin bundled yet** (ADR-0035
 * Phase 2 adds Health Connect, Phase 3 adds HealthKit), so on web — and on native until
 * a plugin is registered via `setHealthPlugin` — `isHealthSyncAvailable()` is false and
 * the Settings card renders the honest "available in the mobile app" fallback. Never a
 * control that silently does nothing (the reminders-seam lesson, ADR-0024/0029).
 *
 * The seam is an injectable accessor: a future plugin satisfies `HealthPlugin`
 * structurally, and the mapping + sync flow are pure/unit-testable off-device. Every
 * failure is a typed RESULT, not a throw the UI must decode.
 */

import { importWearable } from '../api/endpoints';
import type {
  HealthPlatform,
  WearableMetric,
  WearableSampleIn,
  WearableSourceDevice,
} from '../api/types';
import { getPlatform, isNativePlatform } from '../auth/platform';

/** One mobility sample as a native health plugin hands it to us — already normalized to
 * our closed metric set by the native layer (the native code owns the HealthKit /
 * Health Connect field mapping; this seam owns transport + provenance). */
export interface HealthMobilitySample {
  metric: WearableMetric;
  value: number;
  startISO: string;
  endISO: string;
  sourceDevice: WearableSourceDevice;
  /** True when the phone produced this without a watch — the base tier (ADR-0035). */
  phoneDerived: boolean;
  /** The platform's stable sample id (HKSample.uuid / Health Connect metadata.id). */
  externalId?: string | null;
}

/** The slice of a future Health Connect / HealthKit plugin the seam needs. A real plugin
 * satisfies this structurally (ADR-0024 injectable-accessor pattern). */
export interface HealthPlugin {
  isAvailable(): Promise<boolean>;
  requestPermissions(metrics: WearableMetric[]): Promise<boolean>;
  queryMobility(sinceISO: string): Promise<HealthMobilitySample[]>;
}

/** The metrics we request/read — kept in lockstep with the backend catalog. */
export const HEALTH_METRICS: readonly WearableMetric[] = [
  'wearable_walking_speed',
  'wearable_step_length',
  'wearable_steps',
  'wearable_walking_distance',
  'wearable_walking_asymmetry',
  'wearable_double_support',
  'wearable_walking_steadiness',
];

// Injected by the native bootstrap once a plugin ships (Phase 2/3). Until then null, so
// web AND native-without-a-plugin honestly report unavailable.
let plugin: HealthPlugin | null = null;

export function setHealthPlugin(next: HealthPlugin | null): void {
  plugin = next;
}

/** Which platform store are we on? iOS → Apple Health, Android → Health Connect, else
 * null (web). */
export function healthPlatform(): HealthPlatform | null {
  switch (getPlatform()) {
    case 'ios':
      return 'apple_health';
    case 'android':
      return 'health_connect';
    default:
      return null;
  }
}

/** True only when a real health source can be reached: native + a registered plugin +
 * a known platform store. Drives the Settings card's honest state. */
export function isHealthSyncAvailable(): boolean {
  return isNativePlatform() && plugin !== null && healthPlatform() !== null;
}

/** Pure mapping: a plugin sample → the API payload. Platform is passed in (not read from
 * Capacitor) so the mapping stays pure and testable; the metric determines the unit
 * server-side, so the client never names a unit (the BioMech feet-vs-cm lesson). */
export function toWearableSample(
  sample: HealthMobilitySample,
  platform: HealthPlatform,
): WearableSampleIn {
  return {
    metric: sample.metric,
    value: sample.value,
    effective_start: sample.startISO,
    effective_end: sample.endISO,
    platform,
    source_device: sample.sourceDevice,
    phone_derived: sample.phoneDerived,
    external_id: sample.externalId ?? null,
  };
}

export type HealthSyncResult =
  | { status: 'unavailable' }
  | { status: 'permission-denied' }
  | { status: 'no-data' }
  | { status: 'imported'; imported: number; skipped: number };

/**
 * Read mobility since `sinceISO` and import it. Returns a typed result for every path:
 * unavailable (no plugin/web), permission-denied (OS refusal — a result, not an error),
 * no-data (nothing new), or imported counts. A plugin/bridge/API fault still throws, for
 * the caller's catch.
 */
export async function syncHealth(sinceISO: string): Promise<HealthSyncResult> {
  const platform = healthPlatform();
  if (!isNativePlatform() || plugin === null || platform === null) {
    return { status: 'unavailable' };
  }
  if (!(await plugin.isAvailable())) {
    return { status: 'unavailable' };
  }
  const granted = await plugin.requestPermissions([...HEALTH_METRICS]);
  if (!granted) {
    return { status: 'permission-denied' };
  }
  const raw = await plugin.queryMobility(sinceISO);
  const samples = raw.map((sample) => toWearableSample(sample, platform));
  if (samples.length === 0) {
    return { status: 'no-data' };
  }
  const out = await importWearable(samples);
  return { status: 'imported', imported: out.imported, skipped: out.skipped };
}
