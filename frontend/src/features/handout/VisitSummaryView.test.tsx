/**
 * The shared Visit-Ready Summary render (ADR-0045). Rendered directly (it is presentational —
 * no router or auth) so every branch is exercised: the sourced sections, the co-located
 * non-diagnostic disclaimer AFTER the hero, the window-driven lead-section ordering, the
 * unit-safe lab note, the empty-account honesty state, and the D2-gated change questions.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { VisitSummary } from '../../api/types';
import {
  VISIT_SUMMARY,
  VISIT_SUMMARY_INSUFFICIENT,
  VISIT_SUMMARY_SHEET_LABEL,
  VISIT_SUMMARY_WITH_CHANGE_QUESTIONS,
  visitSummaryForWindow,
} from '../../test/fixtures';
import { VisitSummaryView } from './VisitSummaryView';

function renderView(summary: VisitSummary) {
  return render(
    <VisitSummaryView
      summary={summary}
      heroEyebrow="60 days summary"
      heroAriaLabel="Your summary"
    />,
  );
}

describe('VisitSummaryView', () => {
  it('renders the status hero with the disclaimer co-located immediately after it (role=note)', () => {
    renderView(VISIT_SUMMARY);
    const hero = screen.getByRole('region', { name: /Your summary/ });
    expect(hero).toHaveClass('traj', 'improving');
    expect(screen.getByText('74')).toBeInTheDocument();

    const note = screen.getByRole('note');
    expect(note).toHaveTextContent(/not a diagnosis/);
    // The guardrail sits AFTER the hero (co-located, never above it).
    expect(hero.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders every sourced section with source + date labels', () => {
    renderView(VISIT_SUMMARY);
    // What changed.
    expect(screen.getByRole('heading', { name: 'What changed' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'New lab results' })).toBeInTheDocument();
    expect(screen.getByText(/was steady before and is now improving/)).toBeInTheDocument();
    expect(screen.getByText(/Last check-in was 3 days ago/)).toBeInTheDocument();

    // Symptom sparkline (>=2 points) is an accessible image.
    expect(screen.getByRole('img', { name: /nerve pain over this window/ })).toBeInTheDocument();

    // Function: the single-reading series shows the honest "not enough readings" line.
    expect(screen.getByRole('heading', { name: 'Function & daily living' })).toBeInTheDocument();
    expect(screen.getByText(/Not enough readings to draw a line yet/)).toBeInTheDocument();

    // Balance & gait: latest vs prior, and the no-prior branch.
    expect(screen.getByRole('heading', { name: 'Balance & gait' })).toBeInTheDocument();
    expect(screen.getByText(/No prior value in the record/)).toBeInTheDocument();

    // Labs: latest + prior + numeric delta (scoped to the Labs section — the same analyte also
    // surfaces under "What changed").
    const labs = screen.getByRole('heading', { name: 'Labs' }).closest('section');
    expect(labs).not.toBeNull();
    expect(within(labs as HTMLElement).getByText(/Change: \+0\.3 %/)).toBeInTheDocument();

    // Activity: summary stats only.
    expect(screen.getByRole('heading', { name: 'Activity & glucose' })).toBeInTheDocument();
    expect(screen.getByText(/24 readings\. Average 6\.8 \(range 6\.1–7\.6\)/)).toBeInTheDocument();

    // Placeholder rows (render-only) — medications & patient notes are now CAPTURED (P2), so
    // only emr_notes + nutrition remain "Not yet tracked".
    expect(screen.getAllByText('Not yet tracked')).toHaveLength(2);
    expect(screen.getByText('EMR clinician notes')).toBeInTheDocument();
    expect(screen.getByText('Nutrition')).toBeInTheDocument();

    // The disclosure honesty sheet label.
    expect(screen.getByText(new RegExp(VISIT_SUMMARY_SHEET_LABEL))).toBeInTheDocument();
  });

  it('renders the captured medications & patient-notes sections and the what-changed medication delta (P2)', () => {
    renderView(VISIT_SUMMARY);

    // Medications section: folded current state with a kind chip, active/stopped, dose, and the
    // "You entered" provenance chip (never a device/lab claim).
    const meds = screen
      .getByRole('heading', { name: 'Medications & supplements' })
      .closest('section');
    expect(meds).not.toBeNull();
    expect(within(meds as HTMLElement).getByText('Alpha-lipoic acid')).toBeInTheDocument();
    expect(within(meds as HTMLElement).getByText('Supplement')).toBeInTheDocument();
    expect(within(meds as HTMLElement).getByText('Active')).toBeInTheDocument();
    expect(within(meds as HTMLElement).getByText('Stopped')).toBeInTheDocument();
    expect(within(meds as HTMLElement).getByText(/Current dose: 600 mg/)).toBeInTheDocument();
    expect(within(meds as HTMLElement).getAllByText('You entered').length).toBeGreaterThan(0);

    // Patient notes & events section: the fall with its verbatim note under the "own words" label.
    const notes = screen
      .getByRole('heading', { name: 'Patient notes & events' })
      .closest('section');
    expect(notes).not.toBeNull();
    expect(within(notes as HTMLElement).getByText('Fall')).toBeInTheDocument();
    expect(
      within(notes as HTMLElement).getByText(/Lost my balance stepping off the curb/),
    ).toBeInTheDocument();
    expect(within(notes as HTMLElement).getByText(/In their own words:/)).toBeInTheDocument();

    // What-changed medication delta (descriptive only): names what was recorded, no advice.
    const whatChanged = screen
      .getByRole('heading', { name: 'Medications recorded this window' })
      .closest('.handout-change');
    expect(whatChanged).not.toBeNull();
    expect(
      within(whatChanged as HTMLElement).getByText(/Dose changed \(600 mg\)/),
    ).toBeInTheDocument();
  });

  it('renders the medication & event data-completeness questions (P2)', () => {
    renderView(VISIT_SUMMARY);
    const questions = screen.getByRole('heading', { name: 'Questions to ask' }).closest('section');
    expect(questions).not.toBeNull();
    expect(
      within(questions as HTMLElement).getByText(/confirm it's reflected in the chart/),
    ).toBeInTheDocument();
    expect(
      within(questions as HTMLElement).getByText(/review them with the patient/),
    ).toBeInTheDocument();
  });

  it('renders the data-completeness question and NO change-pointed question by default', () => {
    renderView(VISIT_SUMMARY);
    const questions = screen.getByRole('heading', { name: 'Questions to ask' }).closest('section');
    expect(questions).not.toBeNull();
    expect(
      within(questions as HTMLElement).getByText(/A new long-term blood sugar result was recorded/),
    ).toBeInTheDocument();
    // Change-pointed prompts are the FDA D2-gated set — absent unless the flag is on.
    expect(screen.queryByText(/ask the patient about it/)).not.toBeInTheDocument();
  });

  it('renders change-pointed questions when the backend flag is on', () => {
    renderView(VISIT_SUMMARY_WITH_CHANGE_QUESTIONS);
    expect(
      screen.getByText(/The nerve pain trend direction changed over the last 60 days/),
    ).toBeInTheDocument();
  });

  it('leads with "what changed" on a short window (deterministic DOM order)', () => {
    renderView(visitSummaryForWindow(60));
    const whatChanged = screen.getByRole('heading', { name: 'What changed' });
    const symptoms = screen.getByRole('heading', { name: 'Symptoms' });
    expect(
      whatChanged.compareDocumentPosition(symptoms) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('leads with the trajectory (trend) on a long window', () => {
    renderView(visitSummaryForWindow(365));
    const whatChanged = screen.getByRole('heading', { name: 'What changed' });
    const symptoms = screen.getByRole('heading', { name: 'Symptoms' });
    // Symptoms (the over-time trend) now precedes the diff.
    expect(
      symptoms.compareDocumentPosition(whatChanged) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('shows the honest empty state when there is no composite yet', () => {
    renderView(VISIT_SUMMARY_INSUFFICIENT);
    expect(screen.getByText('Not enough data yet')).toBeInTheDocument();
    // No fabricated trend: no sparkline, no series sections.
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Symptoms' })).not.toBeInTheDocument();
    // What changed still renders its (empty) honesty line and the minimal questions note.
    expect(
      screen.getByText(/Nothing notable changed against the previous window/),
    ).toBeInTheDocument();
    expect(screen.getByText('No prompts flagged for this window.')).toBeInTheDocument();
    expect(screen.getByText(/No check-ins recorded yet/)).toBeInTheDocument();
  });

  it('says "units changed" instead of a delta when a lab unit differs (ADR-0015)', () => {
    const summary: VisitSummary = {
      ...VISIT_SUMMARY,
      // Clear the What-changed new-lab so the only lab row is the unit-changed one.
      what_changed: { ...VISIT_SUMMARY.what_changed, new_labs: [] },
      labs: [
        {
          code: '4548-4',
          label: 'Long-term blood sugar',
          source: 'lab',
          origin: 'ehr_imported',
          unit: 'mmol/mol',
          latest_value: 53,
          latest_at: '2026-07-01T09:00:00Z',
          prior_value: 7,
          prior_at: '2026-03-30T09:00:00Z',
          prior_unit: '%',
          delta: null,
          unit_changed: true,
        },
      ],
    };
    renderView(summary);
    expect(
      screen.getByText(/Units changed between readings — the change is not shown/),
    ).toBeInTheDocument();
    // No fabricated cross-unit number.
    expect(screen.queryByText(/Change:/)).not.toBeInTheDocument();
  });
});
