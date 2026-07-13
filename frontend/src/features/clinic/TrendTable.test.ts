/**
 * Judgment honesty in the cross-source table (pure logic): unjudgeable
 * polarities and single readings say "not judged" — never "stable" — and a
 * true zero delta on a judgeable measure is "no change".
 */

import { describe, expect, it } from 'vitest';
import type { ObservationItem } from '../../api/types';
import { minRenewalDate, renewalDateToExpiresAt } from './CapabilityOrders';
import { buildTrendRows } from './TrendTable';

function reading(
  code: string,
  value: number,
  effectiveAt: string,
  source = 'lab',
): ObservationItem {
  return {
    code,
    display: null,
    value,
    value_text: null,
    unit: null,
    effective_at: effectiveAt,
    source,
    status: 'final',
  };
}

describe('buildTrendRows', () => {
  it('judges rising higher-is-better as better and rising lower-is-better as worse', () => {
    const rows = buildTrendRows([
      reading('biomech_balance_score', 60, '2026-06-01T10:00:00Z', 'biomech'),
      reading('biomech_balance_score', 65, '2026-07-01T10:00:00Z', 'biomech'),
      reading('4548-4', 7.1, '2026-06-01T10:00:00Z'),
      reading('4548-4', 7.8, '2026-07-01T10:00:00Z'),
    ]);
    expect(rows.find((row) => row.code === 'biomech_balance_score')?.judgment).toBe('better');
    const hba1c = rows.find((row) => row.code === '4548-4');
    expect(hba1c?.judgment).toBe('worse');
    expect(hba1c?.delta).toBeCloseTo(0.7);
  });

  it('never judges unknown or in-range polarities, even with a clear delta', () => {
    const rows = buildTrendRows([
      // in_range_is_better: a delta alone cannot be judged without the range.
      reading('2345-7', 90, '2026-06-01T10:00:00Z'),
      reading('2345-7', 140, '2026-07-01T10:00:00Z'),
      // unknown polarity: tracked but never judged.
      reading('biomech_cadence', 100, '2026-06-01T10:00:00Z', 'biomech'),
      reading('biomech_cadence', 90, '2026-07-01T10:00:00Z', 'biomech'),
    ]);
    for (const row of rows) {
      expect(row.judgment).toBe('not judged');
      expect(row.judgment).not.toBe('stable');
    }
  });

  it('marks a single reading as not judged with a null delta', () => {
    const rows = buildTrendRows([reading('4548-4', 7.2, '2026-06-20T09:00:00Z')]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.delta).toBeNull();
    expect(rows[0]?.judgment).toBe('not judged');
  });

  it('calls a zero delta on a judgeable measure "no change", not "stable"', () => {
    const rows = buildTrendRows([
      reading('biomech_gait_speed', 1.2, '2026-06-01T10:00:00Z', 'biomech'),
      reading('biomech_gait_speed', 1.2, '2026-07-01T10:00:00Z', 'biomech'),
    ]);
    expect(rows[0]?.judgment).toBe('no change');
  });

  it('uses the backend display name for a code outside the UI registry', () => {
    // '718-7' is not in signalMeta's registry: the Signal column must show the
    // backend's display — 'Hemoglobin' — not the raw LOINC code.
    const rows = buildTrendRows([
      { ...reading('718-7', 14.1, '2026-07-01T10:00:00Z'), display: 'Hemoglobin' },
      { ...reading('718-7', 13.2, '2026-06-01T10:00:00Z'), display: 'Hemoglobin' },
    ]);
    expect(rows[0]?.name).toBe('Hemoglobin');
  });

  it('withholds the delta and judgment across a unit change', () => {
    // Same LOINC arriving as 7.2 '%' then 53 'mmol/mol': 45.8 is not a change.
    const rows = buildTrendRows([
      { ...reading('4548-4', 7.2, '2026-06-01T10:00:00Z'), unit: '%' },
      { ...reading('4548-4', 53, '2026-07-01T10:00:00Z'), unit: 'mmol/mol' },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.delta).toBeNull();
    expect(rows[0]?.unitChanged).toBe(true);
    expect(rows[0]?.judgment).toBe('not judged');
  });

  it('skips text-only results entirely', () => {
    const textOnly: ObservationItem = {
      ...reading('4548-4', 0, '2026-06-20T09:00:00Z'),
      value: null,
      value_text: 'specimen rejected',
    };
    expect(buildTrendRows([textOnly])).toHaveLength(0);
  });
});

describe('renewalDateToExpiresAt', () => {
  it('expires at the end of the chosen day, UTC (timezone-aware for the backend)', () => {
    expect(renewalDateToExpiresAt('2026-08-06')).toBe('2026-08-06T23:59:59Z');
  });
});

describe('minRenewalDate', () => {
  it('floors the date input at tomorrow in the local calendar', () => {
    expect(minRenewalDate(new Date(2026, 6, 13, 15, 30))).toBe('2026-07-14');
  });

  it('rolls over month and year boundaries', () => {
    expect(minRenewalDate(new Date(2026, 11, 31, 8, 0))).toBe('2027-01-01');
  });
});
