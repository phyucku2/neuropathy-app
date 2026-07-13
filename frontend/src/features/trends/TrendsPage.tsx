/**
 * Trends — the graphing centerpiece (mockup screen 4). Observations are
 * grouped by code; the patient picks a metric from those actually present in
 * their data. Each chart states its direction-of-better in plain language
 * (from signal semantics), and a code with fewer than 2 numeric points shows
 * a visible empty state instead of a misleading line.
 */

import { useCallback, useMemo, useState } from 'react';
import { getObservations } from '../../api/endpoints';
import type { ObservationItem } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { formatDayYear, formatValue } from '../../lib/format';
import {
  directionOfBetter,
  displayUnit,
  judgeChange,
  labelFor,
  sourceLabel,
} from '../../lib/signalMeta';
import { useApi } from '../../lib/useApi';
import { TrendChart, type TrendPoint } from './TrendChart';

const PAGE_LIMIT = 100;

/** A chartable point that keeps its reading's raw unit string. */
export interface SeriesPoint extends TrendPoint {
  unit: string | null;
}

interface MetricSeries {
  code: string;
  name: string;
  unitText: string;
  source: string;
  points: SeriesPoint[]; // ascending by time
  latestAt: number;
}

export function groupByCode(items: ObservationItem[]): MetricSeries[] {
  const byCode = new Map<string, { items: ObservationItem[]; latest: ObservationItem }>();
  for (const item of items) {
    if (item.value === null) {
      continue; // text-only results are listed elsewhere, never charted
    }
    const existing = byCode.get(item.code);
    if (existing === undefined) {
      byCode.set(item.code, { items: [item], latest: item });
    } else {
      existing.items.push(item);
      if (Date.parse(item.effective_at) > Date.parse(existing.latest.effective_at)) {
        existing.latest = item;
      }
    }
  }
  const series: MetricSeries[] = [];
  for (const [code, group] of byCode) {
    const points = group.items
      .map((item) => ({
        t: Date.parse(item.effective_at),
        value: item.value as number,
        unit: item.unit,
      }))
      .sort((a, b) => a.t - b.t);
    series.push({
      code,
      name: labelFor(code, group.latest.display),
      unitText: displayUnit(group.latest.unit),
      source: group.latest.source,
      points,
      latestAt: points[points.length - 1]?.t ?? 0,
    });
  }
  return series.sort((a, b) => b.latestAt - a.latestAt);
}

/**
 * Change between the two most recent readings — the ONE delta both surfaces
 * (patient DeltaBadge, clinician TrendTable) show. When the readings carry
 * different unit strings (e.g. HbA1c arriving as '%' then 'mmol/mol'), the
 * numbers are incomparable: no delta is produced and callers show a
 * "unit changed" note instead of a judgment.
 */
export function changeSincePrevious(points: SeriesPoint[]): {
  delta: number | null;
  unitChanged: boolean;
} {
  const last = points[points.length - 1];
  const previous = points[points.length - 2];
  if (last === undefined || previous === undefined) {
    return { delta: null, unitChanged: false };
  }
  if (last.unit !== previous.unit) {
    return { delta: null, unitChanged: true };
  }
  return { delta: last.value - previous.value, unitChanged: false };
}

function DeltaBadge({ code, points, unitText }: MetricSeries) {
  const last = points[points.length - 1];
  if (last === undefined) {
    return null;
  }
  const { delta, unitChanged } = changeSincePrevious(points);
  const judged = delta === null ? 'neutral' : judgeChange(code, delta);
  const deltaClass =
    judged === 'better' ? 'delta up' : judged === 'worse' ? 'delta down' : 'delta flat';
  // The judgment is a visible word, never color alone; for lower-is-better
  // measures the arrow and the color would otherwise contradict each other.
  // Unjudged (unknown-polarity) measures show no judgment word at all.
  const judgedWord = judged === 'better' ? 'better' : judged === 'worse' ? 'worse' : null;
  const spokenJudgment =
    judged === 'better' ? ' — improving' : judged === 'worse' ? ' — getting worse' : '';
  return (
    <div className="big-value">
      <span className="num">{formatValue(last.value)}</span>
      {unitText !== '' && <span className="muted">{unitText}</span>}
      {delta !== null && delta !== 0 && (
        <span
          className={deltaClass}
          role="img"
          aria-label={`${delta > 0 ? 'up' : 'down'} ${formatValue(Math.abs(delta))}${spokenJudgment}`}
        >
          {delta > 0 ? '↑' : '↓'} {formatValue(Math.abs(delta))}
          {judgedWord !== null && ` · ${judgedWord}`}
        </span>
      )}
      {unitChanged && <span className="muted">unit changed — change not judged</span>}
      <span className="muted">latest, {formatDayYear(last.t)}</span>
    </div>
  );
}

export function TrendsPage() {
  const fetchPage = useCallback(() => getObservations({ limit: PAGE_LIMIT }), []);
  const { data: page, error, loading } = useApi(fetchPage);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);

  const series = useMemo(() => (page === null ? [] : groupByCode(page.items)), [page]);

  if (loading) {
    return <Loading label="Loading your readings…" />;
  }
  if (error !== null || page === null) {
    return <ErrorNotice>{error ?? 'Something went wrong. Please try again.'}</ErrorNotice>;
  }

  if (series.length === 0) {
    return (
      <div>
        <h1>Trends</h1>
        <div className="empty-state">
          <p style={{ marginTop: 0 }}>
            <b>No readings yet.</b>
          </p>
          <p style={{ marginBottom: 0 }}>
            Add a BioMech report or do today&apos;s check-in, and your trends will appear here.
          </p>
        </div>
      </div>
    );
  }

  const selected = series.find((entry) => entry.code === selectedCode) ?? series[0];
  if (selected === undefined) {
    return null;
  }

  return (
    <div>
      <h1>Trends</h1>
      <div className="metric-picker" role="group" aria-label="Pick a measure">
        {series.map((entry) => (
          <button
            key={entry.code}
            type="button"
            className="metric-chip"
            aria-pressed={entry.code === selected.code}
            onClick={() => {
              setSelectedCode(entry.code);
            }}
          >
            {entry.name}
          </button>
        ))}
      </div>

      <div className="card">
        <div className="eyebrow">
          {sourceLabel(selected.source)} ·{' '}
          {selected.points.length === 1
            ? '1 reading'
            : `${String(selected.points.length)} readings`}
        </div>
        <h2>{selected.name}</h2>
        <DeltaBadge {...selected} />
        {selected.points.length >= 2 ? (
          <TrendChart name={selected.name} unitText={selected.unitText} points={selected.points} />
        ) : (
          <div className="empty-state">
            Not enough readings to draw a trend yet — one more and the line appears.
          </div>
        )}
        <p className="muted" style={{ marginBottom: 0 }}>
          {directionOfBetter(selected.code)}
        </p>
        <div style={{ marginTop: 10 }}>
          <span className="chip">from {sourceLabel(selected.source)}</span>
          <span className="chip">
            {selected.points.length === 1
              ? '1 data point'
              : `${String(selected.points.length)} data points`}
          </span>
        </div>
      </div>

      {page.total > PAGE_LIMIT && (
        <p className="muted centered">Showing your most recent {String(PAGE_LIMIT)} readings.</p>
      )}
    </div>
  );
}
