/**
 * The dependency-free sparkline (ADR-0045): renders an accessible inline-SVG polyline from >=2
 * points, draws nothing below that (the caller shows an honest empty state), and never divides
 * by zero on a flat series.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SparkPoint } from '../../api/types';
import { Sparkline } from './Sparkline';

const points: SparkPoint[] = [
  { at: '2026-05-20T08:00:00Z', value: 6 },
  { at: '2026-06-10T08:00:00Z', value: 5 },
  { at: '2026-07-12T08:00:00Z', value: 4 },
];

describe('Sparkline', () => {
  it('renders an accessible polyline with one coordinate per point', () => {
    render(<Sparkline points={points} label="nerve pain over this window" />);
    const svg = screen.getByRole('img', { name: 'nerve pain over this window' });
    const polyline = svg.querySelector('polyline');
    expect(polyline).not.toBeNull();
    // Three points → three "x,y" pairs.
    expect((polyline?.getAttribute('points') ?? '').trim().split(/\s+/)).toHaveLength(3);
    expect(polyline?.getAttribute('stroke')).toBe('currentColor');
  });

  it('draws nothing for fewer than two points (the caller shows the empty state)', () => {
    const { container } = render(
      <Sparkline points={[{ at: '2026-05-20T08:00:00Z', value: 7 }]} label="single" />,
    );
    expect(container.querySelector('svg')).toBeNull();
  });

  it('handles a flat series without dividing by zero', () => {
    render(
      <Sparkline
        points={[
          { at: '2026-05-20T08:00:00Z', value: 5 },
          { at: '2026-07-12T08:00:00Z', value: 5 },
        ]}
        label="flat"
      />,
    );
    const polyline = screen.getByRole('img', { name: 'flat' }).querySelector('polyline');
    // No NaN in the coordinate string (span defaulted to 1).
    expect(polyline?.getAttribute('points')).not.toContain('NaN');
  });
});
