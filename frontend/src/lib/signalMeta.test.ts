import { describe, expect, it } from 'vitest';
import { formatDay, formatDayYear, formatValue } from './format';
import {
  directionOfBetter,
  displayUnit,
  judgeChange,
  labelFor,
  polarityFor,
  sourceLabel,
} from './signalMeta';

describe('signalMeta', () => {
  it('mirrors the backend directionality registry for known codes', () => {
    expect(polarityFor('biomech_balance_score')).toBe('higher_is_better');
    expect(polarityFor('biomech_gait_score')).toBe('higher_is_better');
    expect(polarityFor('wearable_walking_asymmetry')).toBe('lower_is_better');
    expect(polarityFor('4548-4')).toBe('lower_is_better'); // HbA1c by LOINC code
    expect(polarityFor('2132-9')).toBe('in_range_is_better'); // B12
    expect(polarityFor('biomech_cadence')).toBe('unknown');
    expect(polarityFor('BIOMECH_BALANCE_SCORE')).toBe('higher_is_better'); // case-insensitive
    expect(polarityFor('made_up_code')).toBe('unknown');
  });

  it('states direction-of-better in plain language, never judging unknown codes', () => {
    expect(directionOfBetter('biomech_balance_score')).toBe('Higher is better for this measure.');
    expect(directionOfBetter('wearable_walking_asymmetry')).toBe(
      'Lower is better for this measure.',
    );
    expect(directionOfBetter('2345-7')).toBe('Best when inside the normal range.');
    expect(directionOfBetter('biomech_cadence')).toContain('not judged better or worse');
  });

  it('judges deltas against polarity', () => {
    expect(judgeChange('biomech_balance_score', 8)).toBe('better');
    expect(judgeChange('biomech_balance_score', -3)).toBe('worse');
    expect(judgeChange('wearable_walking_asymmetry', -1.5)).toBe('better');
    expect(judgeChange('wearable_walking_asymmetry', 1.5)).toBe('worse');
    expect(judgeChange('biomech_balance_score', 0)).toBe('neutral');
    expect(judgeChange('2132-9', 40)).toBe('neutral'); // in-range: never judged by delta
    expect(judgeChange('made_up_code', 2)).toBe('neutral');
  });

  it('labels codes from the display, the registry, or a humanized fallback', () => {
    expect(labelFor('anything', 'Server display')).toBe('Server display');
    expect(labelFor('4548-4')).toBe('Long-term blood sugar');
    expect(labelFor('adl_daily_score', null)).toBe('Daily function score');
    expect(labelFor('grip_strength')).toBe('Grip strength');
    expect(labelFor('')).toBe('');
  });

  it('labels sources and cleans UCUM annotation units', () => {
    expect(sourceLabel('biomech')).toBe('BioMech');
    expect(sourceLabel('lab')).toBe('Lab');
    expect(sourceLabel('adl')).toBe('Check-in');
    expect(sourceLabel('emr')).toBe('Your records');
    expect(sourceLabel('device')).toBe('Device');
    expect(displayUnit('{score}')).toBe('score');
    expect(displayUnit('mm/s')).toBe('mm/s');
    expect(displayUnit(null)).toBe('');
  });
});

describe('format', () => {
  it('formats dates in UTC and trims float noise', () => {
    const t = Date.parse('2026-07-02T10:00:00Z');
    expect(formatDay(t)).toBe('Jul 2');
    expect(formatDayYear(t)).toBe('Jul 2, 2026');
    expect(formatValue(11.4)).toBe('11.4');
    expect(formatValue(11.456)).toBe('11.46');
    expect(formatValue(65)).toBe('65');
  });
});
