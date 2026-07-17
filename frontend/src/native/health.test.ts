/**
 * The wearable/phone health seam (ADR-0035 Phase 1): platform routing, availability,
 * the pure sample mapping, and syncHealth's typed results. The plugin + platform are
 * injected/mocked (ADR-0024 seam lesson) so everything is pinned off-device; a denied
 * permission is a RESULT, never a throw; web and no-plugin are honest no-ops.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../auth/platform', () => ({
  isNativePlatform: vi.fn(() => true),
  getPlatform: vi.fn(() => 'ios'),
}));
vi.mock('../api/endpoints', () => ({
  importWearable: vi.fn(async () => ({ imported: 0, skipped: 0 })),
}));

import { importWearable } from '../api/endpoints';
import { getPlatform, isNativePlatform } from '../auth/platform';
import {
  HEALTH_METRICS,
  MMOL_L_TO_MG_DL,
  healthPlatform,
  isHealthSyncAvailable,
  setHealthPlugin,
  syncHealth,
  toGlucoseSample,
  toWearableSample,
} from './health';
import type { HealthGlucoseSample, HealthMobilitySample, HealthPlugin } from './health';

const nativeMock = vi.mocked(isNativePlatform);
const platformMock = vi.mocked(getPlatform);
const importMock = vi.mocked(importWearable);

function sample(over: Partial<HealthMobilitySample> = {}): HealthMobilitySample {
  return {
    metric: 'wearable_walking_speed',
    value: 1.1,
    startISO: '2026-07-15T08:00:00.000Z',
    endISO: '2026-07-15T08:03:00.000Z',
    sourceDevice: 'iphone',
    phoneDerived: true,
    externalId: 'HK-1',
    ...over,
  };
}

function fakePlugin(over: Partial<HealthPlugin> = {}): HealthPlugin {
  return {
    isAvailable: vi.fn(async () => true),
    requestPermissions: vi.fn(async () => true),
    queryMobility: vi.fn(async () => [sample()]),
    ...over,
  };
}

beforeEach(() => {
  nativeMock.mockReturnValue(true);
  platformMock.mockReturnValue('ios');
  importMock.mockReset().mockResolvedValue({ imported: 1, skipped: 0 });
  setHealthPlugin(null);
});

describe('healthPlatform', () => {
  it('routes iOS → Apple Health, Android → Health Connect, web → null', () => {
    platformMock.mockReturnValue('ios');
    expect(healthPlatform()).toBe('apple_health');
    platformMock.mockReturnValue('android');
    expect(healthPlatform()).toBe('health_connect');
    platformMock.mockReturnValue('web');
    expect(healthPlatform()).toBeNull();
  });
});

describe('isHealthSyncAvailable', () => {
  it('is true only when native AND a plugin is registered AND a platform store exists', () => {
    nativeMock.mockReturnValue(false);
    setHealthPlugin(fakePlugin());
    expect(isHealthSyncAvailable()).toBe(false); // web

    nativeMock.mockReturnValue(true);
    setHealthPlugin(null);
    expect(isHealthSyncAvailable()).toBe(false); // no plugin yet

    setHealthPlugin(fakePlugin());
    expect(isHealthSyncAvailable()).toBe(true);

    platformMock.mockReturnValue('web'); // native shell but unknown store
    expect(isHealthSyncAvailable()).toBe(false);
  });
});

describe('toWearableSample', () => {
  it('maps fields and defaults a missing external_id to null (the client never names a unit)', () => {
    expect(toWearableSample(sample({ externalId: undefined }), 'apple_health')).toEqual({
      metric: 'wearable_walking_speed',
      value: 1.1,
      effective_start: '2026-07-15T08:00:00.000Z',
      effective_end: '2026-07-15T08:03:00.000Z',
      platform: 'apple_health',
      source_device: 'iphone',
      phone_derived: true,
      external_id: null,
    });
  });
});

describe('toGlucoseSample', () => {
  function glucose(over: Partial<HealthGlucoseSample> = {}): HealthGlucoseSample {
    return {
      value: 6.5,
      unit: 'mmol/L',
      startISO: '2026-07-15T08:00:00.000Z',
      endISO: '2026-07-15T08:00:00.000Z',
      sourceDevice: 'iphone',
      phoneDerived: true,
      externalId: 'CGM-1',
      ...over,
    };
  }

  it('converts Health Connect mmol/L to canonical mg/dL at the edge', () => {
    const out = toGlucoseSample(glucose({ value: 6.5, unit: 'mmol/L' }), 'health_connect');
    expect(out.metric).toBe('blood_glucose');
    expect(out.platform).toBe('health_connect');
    // 6.5 mmol/L * 18.0182 = 117.1183 mg/dL — the client always sends mg/dL.
    expect(out.value).toBeCloseTo(6.5 * MMOL_L_TO_MG_DL, 6);
    expect(out.external_id).toBe('CGM-1');
  });

  it('passes a HealthKit mg/dL reading through unchanged and defaults external_id to null', () => {
    const out = toGlucoseSample(
      glucose({ value: 120, unit: 'mg/dL', externalId: undefined }),
      'apple_health',
    );
    expect(out.value).toBe(120);
    expect(out.metric).toBe('blood_glucose');
    expect(out.external_id).toBeNull();
  });

  it('rejects an unknown unit WITHOUT echoing the reading (glucose is PHI)', () => {
    const bad = glucose({ value: 137, unit: 'ng/mL' });
    expect(() => toGlucoseSample(bad, 'apple_health')).toThrow(/Unsupported glucose unit/);
    let message = '';
    try {
      toGlucoseSample(bad, 'apple_health');
    } catch (err) {
      message = String(err);
    }
    expect(message).toContain('ng/mL'); // names the offending unit
    expect(message).not.toContain('137'); // but never the measured reading
  });
});

describe('syncHealth', () => {
  it('is unavailable with no plugin, and never calls the API', async () => {
    setHealthPlugin(null);
    expect(await syncHealth('2026-07-01T00:00:00Z')).toEqual({ status: 'unavailable' });
    expect(importMock).not.toHaveBeenCalled();
  });

  it('is unavailable on web even if a plugin is registered', async () => {
    nativeMock.mockReturnValue(false);
    setHealthPlugin(fakePlugin());
    expect(await syncHealth('s')).toEqual({ status: 'unavailable' });
  });

  it('is unavailable when the plugin reports the store is unavailable', async () => {
    setHealthPlugin(fakePlugin({ isAvailable: vi.fn(async () => false) }));
    expect(await syncHealth('s')).toEqual({ status: 'unavailable' });
  });

  it('returns permission-denied (a result, not a throw) and never imports', async () => {
    setHealthPlugin(fakePlugin({ requestPermissions: vi.fn(async () => false) }));
    expect(await syncHealth('s')).toEqual({ status: 'permission-denied' });
    expect(importMock).not.toHaveBeenCalled();
  });

  it('returns no-data when the store has nothing new', async () => {
    setHealthPlugin(fakePlugin({ queryMobility: vi.fn(async () => []) }));
    expect(await syncHealth('s')).toEqual({ status: 'no-data' });
    expect(importMock).not.toHaveBeenCalled();
  });

  it('requests the full metric set, maps every sample, and returns the imported counts', async () => {
    const plugin = fakePlugin({
      queryMobility: vi.fn(async () => [
        sample(),
        sample({ metric: 'wearable_step_length', value: 0.6, externalId: 'HK-2' }),
      ]),
    });
    setHealthPlugin(plugin);
    importMock.mockResolvedValue({ imported: 2, skipped: 0 });

    const result = await syncHealth('2026-07-01T00:00:00Z');

    expect(result).toEqual({ status: 'imported', imported: 2, skipped: 0 });
    expect(plugin.requestPermissions).toHaveBeenCalledWith([...HEALTH_METRICS]);
    expect(importMock).toHaveBeenCalledWith([
      expect.objectContaining({
        metric: 'wearable_walking_speed',
        platform: 'apple_health',
        external_id: 'HK-1',
      }),
      expect.objectContaining({
        metric: 'wearable_step_length',
        value: 0.6,
        external_id: 'HK-2',
      }),
    ]);
  });
});
