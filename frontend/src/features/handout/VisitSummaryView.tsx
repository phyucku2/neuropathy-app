/**
 * The Visit-Ready Summary render (ADR-0045), shared by the patient print (HandoutPage) and the
 * clinician-side Summary tab (PatientDetailPage) — the SAME `VisitSummary` behind both, so the
 * two surfaces can never drift (mirrors how TrajectoryView is shared, ADR-0012).
 *
 * It is a pure, deterministic re-presentation of the patient's OWN recorded data. It makes no
 * clinical claim: the non-diagnostic disclaimer is co-located directly under the status hero,
 * every datum carries its source + date, and the "questions to ask" are the backend's template
 * prompts (never advice) rendered verbatim. Which block leads — the "what changed" diff or the
 * over-time trend — is driven by `lead_section` (computed from the window), never branched here
 * beyond that one ordering swap.
 */

import type { ReactNode } from 'react';
import type {
  ActivityStat,
  Direction,
  LabDelta,
  MedicationChangeDelta,
  MedicationItem,
  PatientEventItem,
  PriorDelta,
  TrendSeries,
  VisitSummary,
} from '../../api/types';
import { SignalRow, TrajectoryHero } from '../../components/TrajectoryView';
import { formatDayYear, formatValue } from '../../lib/format';
import { displayUnit, sourceLabel } from '../../lib/signalMeta';
import { Sparkline } from './Sparkline';

/** Direction word + glyph — conveyed in WORDS as well as a glyph (never colour alone, WCAG
 *  1.4.1). `insufficient_data` never becomes a fabricated "steady" claim. */
const DIRECTION_META: Record<Direction, { glyph: string; word: string; cls: string }> = {
  improving: { glyph: '↑', word: 'improving', cls: 'up' },
  declining: { glyph: '↓', word: 'declining', cls: 'down' },
  stable: { glyph: '→', word: 'steady', cls: 'flat' },
  insufficient_data: { glyph: '·', word: 'not enough data', cls: 'unjudged' },
};

function DirectionTag({ direction }: { direction: Direction }) {
  const meta = DIRECTION_META[direction];
  return (
    <span className={`hd-dir ${meta.cls}`} role="img" aria-label={meta.word}>
      {meta.glyph} {meta.word}
    </span>
  );
}

/** "9 on Jul 2, 2026", or null when there is no reading to describe. */
function valueAt(value: number | null, at: string | null, unit = ''): string | null {
  if (value === null || at === null) {
    return null;
  }
  const suffix = unit === '' ? '' : ` ${unit}`;
  return `${formatValue(value)}${suffix} on ${formatDayYear(Date.parse(at))}`;
}

/** "+7" / "−7" / "0" — signed change with a real minus glyph, no clinical judgment attached. */
function signed(delta: number): string {
  if (delta > 0) return `+${formatValue(delta)}`;
  if (delta < 0) return `−${formatValue(Math.abs(delta))}`;
  return '0';
}

function TrendSeriesRow({ series }: { series: TrendSeries }) {
  const start = valueAt(series.start_value, series.start_at);
  const latest = valueAt(series.latest_value, series.latest_at);
  return (
    <div className="handout-row">
      <div className="handout-row-head">
        <span className="handout-metric">{series.label}</span>
        <span className="chip">{sourceLabel(series.source)}</span>
        <DirectionTag direction={series.direction} />
      </div>
      {series.points.length >= 2 ? (
        <Sparkline
          points={series.points}
          label={`${series.label} over this window: ${DIRECTION_META[series.direction].word}`}
        />
      ) : (
        <p className="muted handout-span">Not enough readings to draw a line yet.</p>
      )}
      <p className="handout-span">
        {start === null ? 'Latest' : `From ${start}`}
        {latest === null
          ? ' — no reading in this window'
          : `${start === null ? ' ' : ' → '}${latest}`}
      </p>
    </div>
  );
}

function PriorDeltaRow({ item }: { item: PriorDelta }) {
  const latest = valueAt(item.latest_value, item.latest_at);
  const prior = valueAt(item.prior_value, item.prior_at);
  return (
    <div className="handout-row">
      <div className="handout-row-head">
        <span className="handout-metric">{item.label}</span>
        <span className="chip">{sourceLabel(item.source)}</span>
        <DirectionTag direction={item.direction} />
      </div>
      <p className="handout-span">
        {latest === null ? 'No reading in this window.' : `Latest ${latest}.`}{' '}
        {prior === null ? 'No prior value in the record.' : `Prior ${prior}.`}
      </p>
    </div>
  );
}

function LabDeltaRow({ lab }: { lab: LabDelta }) {
  const unit = displayUnit(lab.unit);
  const priorUnit = displayUnit(lab.prior_unit);
  const latest = valueAt(lab.latest_value, lab.latest_at, unit);
  const prior = valueAt(lab.prior_value, lab.prior_at, priorUnit);
  return (
    <div className="handout-row">
      <div className="handout-row-head">
        <span className="handout-metric">{lab.label}</span>
        <span className="chip">{sourceLabel(lab.source)}</span>
      </div>
      <p className="handout-span">
        {latest === null ? 'No reading in this window.' : `Latest ${latest}.`}{' '}
        {prior === null ? 'No prior value in the record.' : `Prior ${prior}.`}
        {lab.unit_changed && ' Units changed between readings — the change is not shown.'}
        {lab.delta !== null && ` Change: ${signed(lab.delta)}${unit === '' ? '' : ` ${unit}`}.`}
      </p>
    </div>
  );
}

function ActivityStatRow({ stat }: { stat: ActivityStat }) {
  const latestAt = stat.latest_at === null ? null : formatDayYear(Date.parse(stat.latest_at));
  return (
    <div className="handout-row">
      <div className="handout-row-head">
        <span className="handout-metric">{stat.label}</span>
        <span className="chip">{sourceLabel(stat.source)}</span>
      </div>
      <p className="handout-span">
        {stat.count === 1 ? '1 reading' : `${String(stat.count)} readings`}.
        {stat.mean !== null && ` Average ${formatValue(stat.mean)}`}
        {stat.min !== null &&
          stat.max !== null &&
          ` (range ${formatValue(stat.min)}–${formatValue(stat.max)})`}
        {stat.mean !== null && '.'}
        {latestAt !== null && ` Latest ${latestAt}.`}
      </p>
    </div>
  );
}

/** Friendly labels for the patient-entered medication vocabulary (ADR-0045 P2). Fall back to the
 *  raw value so an unknown future kind/type/change still renders rather than vanishing. */
const KIND_LABEL: Record<string, string> = {
  prescription: 'Prescription',
  otc: 'Over-the-counter',
  supplement: 'Supplement',
};
const CHANGE_LABEL: Record<string, string> = {
  added: 'Added',
  dose_changed: 'Dose changed',
  stopped: 'Stopped',
};

/** "50 mg" / "1 tablet twice daily" / null — the descriptive dose line, no judgment attached. */
function medDose(amount: number | null, unit: string | null, text: string | null): string | null {
  if (text !== null && text.trim() !== '') {
    return text;
  }
  if (amount !== null) {
    const value = formatValue(amount);
    return unit !== null && unit.trim() !== '' ? `${value} ${unit}` : value;
  }
  return null;
}

function MedicationRow({ item }: { item: MedicationItem }) {
  const dose = medDose(item.current_dose_amount, item.current_dose_unit, item.current_dose_text);
  return (
    <div className="handout-row">
      <div className="handout-row-head">
        <span className="handout-metric">{item.name}</span>
        <span className="chip">{KIND_LABEL[item.kind] ?? item.kind}</span>
        <span className={item.status === 'active' ? 'pill on' : 'pill off'}>
          {item.status === 'active' ? 'Active' : 'Stopped'}
        </span>
        <span className="chip">{sourceLabel('medication')}</span>
      </div>
      <p className="handout-span">
        {dose === null ? 'No dose recorded.' : `Current dose: ${dose}.`}
        {item.prescriber !== null &&
          item.prescriber.trim() !== '' &&
          ` Prescriber: ${item.prescriber}.`}{' '}
        Started {formatDayYear(Date.parse(item.started_on))}.
      </p>
    </div>
  );
}

function PatientEventRow({ item }: { item: PatientEventItem }) {
  return (
    <div className="handout-row">
      <div className="handout-row-head">
        <span className="handout-metric">{item.display}</span>
        <span className="chip">{formatDayYear(Date.parse(item.effective_at))}</span>
        <span className="chip">{sourceLabel('event')}</span>
      </div>
      {item.note !== null && item.note.trim() !== '' && (
        <p className="handout-span">
          <span className="muted">In their own words: </span>
          {/* The note is the patient's own words — rendered verbatim as plain text. */}
          {item.note}
        </p>
      )}
    </div>
  );
}

function MedicationChangeDeltaRow({ change }: { change: MedicationChangeDelta }) {
  const dose = medDose(change.dose_amount, change.dose_unit, change.dose_text);
  return (
    <p className="handout-span">
      <b>{change.name}</b> — {CHANGE_LABEL[change.change_type] ?? change.change_type}
      {dose !== null && ` (${dose})`} on {formatDayYear(Date.parse(change.effective_at))}{' '}
      <span className="chip">{sourceLabel('medication')}</span>
    </p>
  );
}

/** A titled card that renders only when it has rows — an empty account shows no empty cards. */
function SeriesCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card handout-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function WhatChangedSection({ summary }: { summary: VisitSummary }) {
  const { new_labs, symptom_trend, adherence, latest_biomech, medication_changes } =
    summary.what_changed;
  const changedSymptoms = symptom_trend.filter((entry) => entry.changed);
  const gapLabel =
    adherence.days_since_last_checkin === null
      ? 'No check-ins recorded yet.'
      : adherence.days_since_last_checkin === 0
        ? 'Last check-in was today.'
        : `Last check-in was ${String(adherence.days_since_last_checkin)} day${
            adherence.days_since_last_checkin === 1 ? '' : 's'
          } ago.`;
  const hasHighlights =
    new_labs.length > 0 ||
    changedSymptoms.length > 0 ||
    latest_biomech.length > 0 ||
    medication_changes.length > 0;

  return (
    <section className="card handout-section" aria-labelledby="what-changed-heading">
      <h2 id="what-changed-heading">What changed</h2>
      <p className="muted handout-span">
        Compared with the previous {String(summary.window_days)} days.
      </p>

      {new_labs.length > 0 && (
        <div className="handout-change">
          <h3>New lab results</h3>
          {new_labs.map((lab) => (
            <LabDeltaRow key={`${lab.source}:${lab.code}`} lab={lab} />
          ))}
        </div>
      )}

      {changedSymptoms.length > 0 && (
        <div className="handout-change">
          <h3>Symptom trend changed direction</h3>
          {changedSymptoms.map((entry) => (
            <p key={`${entry.source}:${entry.code}`} className="handout-span">
              <b>{entry.label}</b> was {DIRECTION_META[entry.prior_direction].word} before and is
              now {DIRECTION_META[entry.current_direction].word}{' '}
              <span className="chip">{sourceLabel(entry.source)}</span>
            </p>
          ))}
        </div>
      )}

      {latest_biomech.length > 0 && (
        <div className="handout-change">
          <h3>Latest balance &amp; gait vs prior</h3>
          {latest_biomech.map((item) => (
            <PriorDeltaRow key={`${item.source}:${item.code}`} item={item} />
          ))}
        </div>
      )}

      {medication_changes.length > 0 && (
        <div className="handout-change">
          <h3>Medications recorded this window</h3>
          {/* Descriptive only (ADR-0045 P2): what the patient recorded, so the clinician can
              confirm it's in the chart — never a reconciliation, interaction check, or advice. */}
          {medication_changes.map((change) => (
            <MedicationChangeDeltaRow
              key={`${change.medication_id}:${change.change_type}:${change.effective_at}`}
              change={change}
            />
          ))}
        </div>
      )}

      <p className="handout-span muted">
        {gapLabel} {String(adherence.checkins_in_window)} check-in
        {adherence.checkins_in_window === 1 ? '' : 's'} in this window,{' '}
        {String(adherence.checkins_in_prior_window)} in the window before.
      </p>

      {!hasHighlights && (
        <p className="handout-span">Nothing notable changed against the previous window.</p>
      )}
    </section>
  );
}

function TrendSections({ summary }: { summary: VisitSummary }) {
  return (
    <>
      {summary.symptoms.length > 0 && (
        <SeriesCard title="Symptoms">
          {summary.symptoms.map((series) => (
            <TrendSeriesRow key={`${series.source}:${series.code}`} series={series} />
          ))}
        </SeriesCard>
      )}
      {summary.function.length > 0 && (
        <SeriesCard title="Function & daily living">
          {summary.function.map((series) => (
            <TrendSeriesRow key={`${series.source}:${series.code}`} series={series} />
          ))}
        </SeriesCard>
      )}
      {summary.balance_gait.length > 0 && (
        <SeriesCard title="Balance & gait">
          {summary.balance_gait.map((item) => (
            <PriorDeltaRow key={`${item.source}:${item.code}`} item={item} />
          ))}
        </SeriesCard>
      )}
      {summary.labs.length > 0 && (
        <SeriesCard title="Labs">
          {summary.labs.map((lab) => (
            <LabDeltaRow key={`${lab.source}:${lab.code}`} lab={lab} />
          ))}
        </SeriesCard>
      )}
      {summary.activity.length > 0 && (
        <SeriesCard title="Activity & glucose">
          {summary.activity.map((stat) => (
            <ActivityStatRow key={`${stat.source}:${stat.code}`} stat={stat} />
          ))}
        </SeriesCard>
      )}
      {summary.medications.length > 0 && (
        <SeriesCard title="Medications & supplements">
          {summary.medications.map((item) => (
            <MedicationRow key={item.medication_id} item={item} />
          ))}
        </SeriesCard>
      )}
      {summary.patient_notes.length > 0 && (
        <SeriesCard title="Patient notes & events">
          {summary.patient_notes.map((item, index) => (
            <PatientEventRow
              key={`${item.type}:${item.effective_at}:${String(index)}`}
              item={item}
            />
          ))}
        </SeriesCard>
      )}
    </>
  );
}

function PlaceholdersSection({ rows }: { rows: VisitSummary['placeholders'] }) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <section className="card handout-section">
      <h2>Coming soon</h2>
      <p className="muted handout-span">
        These sections are coming — they will appear here once we can capture them.
      </p>
      {rows.map((row) => (
        <div className="src" key={row.key}>
          <div className="info">
            <b>{row.label}</b>
            <small>{row.phase}</small>
          </div>
          <span className="pill off">Not yet tracked</span>
        </div>
      ))}
    </section>
  );
}

function QuestionsSection({ questions }: { questions: VisitSummary['questions'] }) {
  const { data_completeness, change_pointed } = questions;
  const empty = data_completeness.length === 0 && change_pointed.length === 0;
  return (
    <section className="card handout-section" aria-labelledby="questions-heading">
      <h2 id="questions-heading">Questions to ask</h2>
      <p className="muted handout-span">
        Prompts that point only at what changed in your own data — bring them to your visit.
      </p>
      {data_completeness.length > 0 && (
        <ul className="handout-questions">
          {data_completeness.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      )}
      {change_pointed.length > 0 && (
        <ul className="handout-questions">
          {change_pointed.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      )}
      {empty && <p className="handout-span">No prompts flagged for this window.</p>}
    </section>
  );
}

export function VisitSummaryView({
  summary,
  heroEyebrow,
  heroAriaLabel,
}: {
  summary: VisitSummary;
  heroEyebrow: string;
  heroAriaLabel: string;
}) {
  const whatChanged = <WhatChangedSection summary={summary} />;
  const trends = <TrendSections summary={summary} />;

  return (
    <div className="handout">
      <TrajectoryHero trajectory={summary.status} eyebrow={heroEyebrow} ariaLabel={heroAriaLabel} />
      {/* The non-diagnostic guardrail, co-located directly under the status hero (CLAUDE.md). */}
      <p className="disclaimer" role="note">
        {summary.disclaimer}
      </p>

      {summary.status.signals.length > 0 && (
        <section className="card handout-section">
          <div className="eyebrow">What&apos;s driving it</div>
          {summary.status.signals.map((signal) => (
            <SignalRow key={`${signal.source}:${signal.code}`} signal={signal} />
          ))}
        </section>
      )}
      {summary.status.data_gaps.length > 0 && (
        <section className="card handout-section">
          <div className="eyebrow">Data gaps</div>
          <ul className="muted" style={{ margin: 0, paddingLeft: 20 }}>
            {summary.status.data_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Window-appropriate emphasis (ADR-0045): short windows lead with the diff, the long
          windows (120/365) lead with the over-time trend. One ordering swap, never a UI branch. */}
      {summary.lead_section === 'what_changed' ? (
        <>
          {whatChanged}
          {trends}
        </>
      ) : (
        <>
          {trends}
          {whatChanged}
        </>
      )}

      <PlaceholdersSection rows={summary.placeholders} />
      <QuestionsSection questions={summary.questions} />

      {/* Disclosure honesty (ADR-0031/0045): the printed sheet leaves the app's control. */}
      <p className="sheet-label muted">This sheet is a {summary.sheet_label}.</p>
    </div>
  );
}
