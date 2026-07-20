/**
 * Dependency-free inline-SVG sparkline for the Visit-Ready Summary (ADR-0045). No charting
 * library (recharts stays out of the print bundle), monochrome so it is legible in black-and-
 * white print (the direction is ALSO conveyed in words + a glyph elsewhere, WCAG 1.4.1), and
 * carries an accessible label since the shape alone is not text. Fewer than two points draws
 * nothing — the caller shows an honest "not enough readings" state instead of a flat line.
 */

import type { SparkPoint } from '../../api/types';

const WIDTH = 140;
const HEIGHT = 36;
// Inset so the 2px stroke never clips at the top/bottom of the box.
const PAD_Y = 3;

export function Sparkline({ points, label }: { points: SparkPoint[]; label: string }) {
  if (points.length < 2) {
    return null;
  }
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series has zero span; divide by 1 so it renders as a centered horizontal line.
  const span = max - min || 1;
  const stepX = WIDTH / (points.length - 1);
  const usableHeight = HEIGHT - PAD_Y * 2;

  const coordinates = points
    .map((point, index) => {
      const x = index * stepX;
      const y = PAD_Y + (1 - (point.value - min) / span) * usableHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg
      className="sparkline"
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      <polyline
        points={coordinates}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
