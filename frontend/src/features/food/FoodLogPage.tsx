/**
 * Food & nutrition log (ADR-0042 V2, Phase 1) — a list the patient keeps of what they ate,
 * as RANGED self-tracking estimates. Describe an item, optionally ask for a starting estimate
 * (Phase 1 has no automated source yet, so you enter your own range), review, and save.
 *
 * NON-DIAGNOSTIC, NON-DOSING (co-located note below): food logs are rough estimates for
 * self-tracking. The app never uses them to check, adjust, or recommend anything, and they are
 * NEVER a basis for insulin or medication dosing. Every save is a confirmed estimate.
 *
 * Capability-gated (`log_food`): the write + estimate 409 when the source is turned off,
 * handled here with a pointer to Sources (mirrors MedsPage/AddDataPage).
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, messageFor } from '../../api/client';
import { getFoodLogs, postFoodEstimate, postFoodLog } from '../../api/endpoints';
import type { FoodRange } from '../../api/types';
import { ErrorNotice, Loading, SuccessNotice } from '../../components/StatusMessages';
import { formatDayYear } from '../../lib/format';
import { useApi } from '../../lib/useApi';

/** The patient's LOCAL calendar day as YYYY-MM-DD (never toISOString — that is UTC). */
function todayLocalIso(now = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${String(now.getFullYear())}-${month}-${day}`;
}

/** Parse a numeric field to a number, or null when blank/invalid (so we never send NaN). */
function toNumber(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === '') {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

/** A ranged nutrient for display: "~30–45 g". */
function rangeLabel(range: FoodRange, unit: string): string {
  return range.low === range.high
    ? `~${String(range.low)} ${unit}`
    : `~${String(range.low)}–${String(range.high)} ${unit}`;
}

function CapabilityOffCard() {
  return (
    <div className="card">
      <div className="eyebrow">Turned off</div>
      <h2>Food log is turned off</h2>
      <p className="muted" style={{ marginTop: 0 }}>
        This source is turned off right now, so nothing is being recorded.{' '}
        <Link className="link" to="/settings">
          You can turn it back on in Sources.
        </Link>
      </p>
    </div>
  );
}

function AddFoodForm({ onAdded }: { onAdded: () => void }) {
  const [description, setDescription] = useState('');
  const [portion, setPortion] = useState('');
  const [carbsLow, setCarbsLow] = useState('');
  const [carbsHigh, setCarbsHigh] = useState('');
  const [energyLow, setEnergyLow] = useState('');
  const [energyHigh, setEnergyHigh] = useState('');
  const [effectiveDate, setEffectiveDate] = useState(todayLocalIso());
  const [hint, setHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [featureOff, setFeatureOff] = useState(false);
  const [savedName, setSavedName] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [estimating, setEstimating] = useState(false);

  const carbs = { low: toNumber(carbsLow), high: toNumber(carbsHigh) };
  const carbsValid = carbs.low !== null && carbs.high !== null && carbs.low <= carbs.high;
  // Energy is optional, but if either bound is given both must be, low <= high.
  const energyGiven = energyLow.trim() !== '' || energyHigh.trim() !== '';
  const energy = { low: toNumber(energyLow), high: toNumber(energyHigh) };
  const energyValid =
    !energyGiven || (energy.low !== null && energy.high !== null && energy.low <= energy.high);
  const canSave =
    description.trim() !== '' && portion.trim() !== '' && carbsValid && energyValid && !saving;

  const getEstimate = async () => {
    if (description.trim() === '' || portion.trim() === '') {
      return;
    }
    setEstimating(true);
    setError(null);
    setFeatureOff(false);
    setHint(null);
    try {
      const result = await postFoodEstimate({
        description: description.trim(),
        portion: portion.trim(),
      });
      if (result.estimate === null) {
        setHint(result.note);
      } else {
        setCarbsLow(String(result.estimate.carbs_g.low));
        setCarbsHigh(String(result.estimate.carbs_g.high));
        if (result.estimate.energy_kcal !== null) {
          setEnergyLow(String(result.estimate.energy_kcal.low));
          setEnergyHigh(String(result.estimate.energy_kcal.high));
        }
        setHint(result.note);
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setFeatureOff(true);
      }
      setError(messageFor(cause));
    } finally {
      setEstimating(false);
    }
  };

  const submit = async () => {
    if (!canSave || carbs.low === null || carbs.high === null) {
      return;
    }
    setSaving(true);
    setError(null);
    setFeatureOff(false);
    setSavedName(null);
    try {
      await postFoodLog({
        description: description.trim(),
        portion: portion.trim(),
        carbs_g: { low: carbs.low, high: carbs.high },
        energy_kcal:
          energyGiven && energy.low !== null && energy.high !== null
            ? { low: energy.low, high: energy.high }
            : null,
        effective_date: effectiveDate,
        confirmed: true,
      });
      setSavedName(description.trim());
      setDescription('');
      setPortion('');
      setCarbsLow('');
      setCarbsHigh('');
      setEnergyLow('');
      setEnergyHigh('');
      setEffectiveDate(todayLocalIso());
      setHint(null);
      onAdded();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setFeatureOff(true);
      }
      setError(messageFor(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <div className="eyebrow">Add to your log</div>
      <h2>Log a food</h2>
      {savedName !== null && <SuccessNotice>Logged {savedName}.</SuccessNotice>}
      {hint !== null && (
        <p className="muted" role="note" style={{ marginTop: 0 }}>
          {hint}
        </p>
      )}
      {error !== null && (
        <ErrorNotice>
          {error}
          {featureOff && (
            <>
              {' '}
              <Link className="link" to="/settings">
                You can turn it back on in Sources.
              </Link>
            </>
          )}
        </ErrorNotice>
      )}
      <div className="field">
        <label htmlFor="food-desc">What did you eat?</label>
        <input
          id="food-desc"
          type="text"
          maxLength={120}
          placeholder="e.g. Oatmeal with banana"
          value={description}
          onChange={(event) => {
            setDescription(event.target.value);
          }}
        />
      </div>
      <div className="field">
        <label htmlFor="food-portion">Portion</label>
        <input
          id="food-portion"
          type="text"
          maxLength={60}
          placeholder="e.g. 1 cup"
          value={portion}
          onChange={(event) => {
            setPortion(event.target.value);
          }}
        />
      </div>
      <button
        className="btn ghost"
        type="button"
        disabled={description.trim() === '' || portion.trim() === '' || estimating}
        onClick={() => {
          void getEstimate();
        }}
      >
        {estimating ? 'Checking…' : 'Get a starting estimate'}
      </button>
      <fieldset className="seg-group" style={{ marginTop: 12 }}>
        <legend>Carbohydrates (your best estimate, as a range)</legend>
        <div className="field-row">
          <div className="field">
            <label htmlFor="food-carbs-low">Low (g)</label>
            <input
              id="food-carbs-low"
              type="number"
              inputMode="decimal"
              min={0}
              value={carbsLow}
              onChange={(event) => {
                setCarbsLow(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="food-carbs-high">High (g)</label>
            <input
              id="food-carbs-high"
              type="number"
              inputMode="decimal"
              min={0}
              value={carbsHigh}
              onChange={(event) => {
                setCarbsHigh(event.target.value);
              }}
            />
          </div>
        </div>
      </fieldset>
      <fieldset className="seg-group">
        <legend>Calories (optional, as a range)</legend>
        <div className="field-row">
          <div className="field">
            <label htmlFor="food-energy-low">Low (kcal)</label>
            <input
              id="food-energy-low"
              type="number"
              inputMode="decimal"
              min={0}
              value={energyLow}
              onChange={(event) => {
                setEnergyLow(event.target.value);
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="food-energy-high">High (kcal)</label>
            <input
              id="food-energy-high"
              type="number"
              inputMode="decimal"
              min={0}
              value={energyHigh}
              onChange={(event) => {
                setEnergyHigh(event.target.value);
              }}
            />
          </div>
        </div>
      </fieldset>
      <div className="field">
        <label htmlFor="food-date">Date</label>
        <input
          id="food-date"
          type="date"
          max={todayLocalIso()}
          value={effectiveDate}
          onChange={(event) => {
            setEffectiveDate(event.target.value);
          }}
        />
      </div>
      <button
        className="btn"
        type="button"
        disabled={!canSave}
        onClick={() => {
          void submit();
        }}
      >
        {saving ? 'Saving…' : 'Save this estimate'}
      </button>
    </div>
  );
}

export function FoodLogPage() {
  const { data, error, errorStatus, loading, reload } = useApi(getFoodLogs);

  return (
    <div>
      <h1>Food &amp; nutrition log</h1>
      <p className="muted" style={{ marginTop: 0 }}>
        A log you keep of what you eat, as rough estimates — handy for spotting patterns and sharing
        with your care team.
      </p>
      {/* The non-diagnostic / non-dosing guardrail, co-located with the capture (CLAUDE.md). */}
      <p className="disclaimer" role="note">
        These are rough estimates for self-tracking — never exact, and never a basis for insulin or
        medication dosing. Talk to your care team about what your food and blood sugar mean for you.
      </p>

      {errorStatus === 409 ? (
        <CapabilityOffCard />
      ) : (
        <>
          <AddFoodForm onAdded={reload} />
          {loading && data === null && <Loading label="Loading your log…" />}
          {error !== null && <ErrorNotice>{error}</ErrorNotice>}
          {data !== null && data.items.length === 0 && (
            <p className="muted">Nothing logged yet. Add your first food above.</p>
          )}
          {data?.items.map((item) => (
            <div className="card" key={item.food_id}>
              <div className="handout-row-head">
                <span className="handout-metric">{item.description}</span>
                <span className="chip">{item.portion}</span>
                <span className="chip">Estimate</span>
              </div>
              <p className="handout-span">
                Carbs {rangeLabel(item.carbs_g, 'g')}
                {item.energy_kcal !== null && ` · ${rangeLabel(item.energy_kcal, 'kcal')}`} ·{' '}
                {formatDayYear(Date.parse(item.effective_at))}
              </p>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
