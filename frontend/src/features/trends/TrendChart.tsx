/**
 * The per-metric line chart (chart-quality bar, ADR-0015):
 * - ONE series per chart, colored with brand tokens; no gridlines, no 3D,
 *   never a dual axis.
 * - x = effective_at as a real time axis with a handful of sensible ticks;
 *   y ticks carry the unit.
 * - Accessible: the chart region is role="img" with an aria-label that
 *   summarizes the trend in words; callers show a visible empty state when a
 *   code has fewer than 2 points (this component requires >= 2).
 * - Tooltips show value + unit + date.
 */

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { formatDay, formatDayYear, formatValue } from '../../lib/format';

export interface TrendPoint {
  /** effective_at as epoch milliseconds. */
  t: number;
  value: number;
}

const LINE_COLOR = '#2E6DA4'; // --color-brand-blue
const AXIS_COLOR = '#556677'; // --color-text-secondary
const BASELINE_COLOR = '#D3DEE8'; // --color-border

/** Up to `count` evenly spaced tick positions across the time range. */
export function timeTicks(points: TrendPoint[], count = 4): number[] {
  const first = points[0];
  const last = points[points.length - 1];
  if (first === undefined || last === undefined || first.t === last.t) {
    return first === undefined ? [] : [first.t];
  }
  if (points.length <= count) {
    return points.map((point) => point.t);
  }
  const span = last.t - first.t;
  return Array.from({ length: count }, (_, i) => first.t + Math.round((span * i) / (count - 1)));
}

/** Plain-language summary of the series — the chart's accessible name. */
export function trendAriaLabel(name: string, unitText: string, points: TrendPoint[]): string {
  const first = points[0];
  const last = points[points.length - 1];
  if (first === undefined || last === undefined) {
    return `${name}: no readings yet`;
  }
  const unitSuffix = unitText === '' ? '' : ` ${unitText}`;
  const word =
    last.value > first.value ? 'rising' : last.value < first.value ? 'falling' : 'steady';
  const change =
    word === 'steady'
      ? `steady at ${formatValue(last.value)}${unitSuffix}`
      : `${word} from ${formatValue(first.value)} to ${formatValue(last.value)}${unitSuffix}`;
  return (
    `${name}: ${String(points.length)} readings from ${formatDayYear(first.t)} ` +
    `to ${formatDayYear(last.t)}, ${change}`
  );
}

interface TooltipPayloadEntry {
  payload?: TrendPoint;
}

export function ChartTooltip({
  active,
  payload,
  unitText,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  unitText: string;
}) {
  const point = payload?.[0]?.payload;
  if (active !== true || point === undefined) {
    return null;
  }
  return (
    <div className="trend-tooltip">
      <b>
        {formatValue(point.value)}
        {unitText === '' ? '' : ` ${unitText}`}
      </b>
      <br />
      <span className="muted">{formatDayYear(point.t)}</span>
    </div>
  );
}

export function TrendChart({
  name,
  unitText,
  points,
}: {
  name: string;
  unitText: string;
  points: TrendPoint[];
}) {
  return (
    <div className="trend-chart" role="img" aria-label={trendAriaLabel(name, unitText, points)}>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            ticks={timeTicks(points)}
            tickFormatter={formatDay}
            stroke={AXIS_COLOR}
            axisLine={{ stroke: BASELINE_COLOR }}
            tickLine={false}
            fontSize={12}
          />
          <YAxis
            width={52}
            stroke={AXIS_COLOR}
            axisLine={false}
            tickLine={false}
            fontSize={12}
            unit={unitText === '' ? undefined : ` ${unitText}`}
            domain={['auto', 'auto']}
          />
          <Tooltip content={<ChartTooltip unitText={unitText} />} />
          <Line
            type="monotone"
            dataKey="value"
            stroke={LINE_COLOR}
            strokeWidth={3}
            dot={{ r: 4, fill: LINE_COLOR, strokeWidth: 0 }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
