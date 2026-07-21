/**
 * "Updates you send to your loved ones" (ADR-0047 Phase B1) — the patient's per-type
 * opt-in toggles for caregiver alerts, a sibling to CaregiverShareCard on Sources.
 *
 * Every type is DEFAULT OFF: a caregiver only ever receives an update after the patient
 * turns that type on here (and only for what their scope allows — the server gates that
 * too). The copy says plainly what these are (occasional, non-urgent updates) and are
 * not (live monitoring, an emergency channel). Toggling is optimistic with rollback on
 * failure, mirroring the Sources capability rows; the server's message is shown verbatim.
 *
 * 60+ plain language, AA contrast (reuses the verified .src / .tg treatments — no new
 * color pairs), non-diagnostic throughout.
 */

import { useEffect, useState } from 'react';
import { messageFor } from '../../api/client';
import { getCaregiverAlertPreferences, setCaregiverAlertPreference } from '../../api/endpoints';
import type { CaregiverAlertType } from '../../api/types';
import { ErrorNotice, Loading } from '../../components/StatusMessages';
import { ALERT_TYPE_META, ALERT_TYPE_ORDER } from '../caregiver/alertMeta';
import { useApi } from '../../lib/useApi';

function PreferenceRow({
  alertType,
  enabled,
  disabled,
  onToggle,
}: {
  alertType: CaregiverAlertType;
  enabled: boolean;
  disabled: boolean;
  onToggle: (alertType: CaregiverAlertType, next: boolean) => void;
}) {
  const meta = ALERT_TYPE_META[alertType];
  return (
    <div className="src">
      <span className="ic" style={{ background: meta.color }} aria-hidden="true">
        {meta.glyph}
      </span>
      <div className="info">
        <b>{meta.label}</b>
        <small>{enabled ? meta.description : 'Off'}</small>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={meta.label}
        className="tg"
        disabled={disabled}
        onClick={() => {
          onToggle(alertType, !enabled);
        }}
      />
    </div>
  );
}

export function CaregiverAlertPreferencesCard() {
  const { data, error, loading } = useApi(getCaregiverAlertPreferences);
  const [enabledByType, setEnabledByType] = useState<Record<string, boolean> | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingType, setSavingType] = useState<string | null>(null);

  useEffect(() => {
    if (data !== null) {
      setEnabledByType(
        Object.fromEntries(data.preferences.map((pref) => [pref.alert_type, pref.enabled])),
      );
    }
  }, [data]);

  const toggle = async (alertType: CaregiverAlertType, next: boolean) => {
    setSaveError(null);
    setSavingType(alertType);
    // Optimistic flip — rolled back if the server refuses.
    setEnabledByType((current) => (current === null ? current : { ...current, [alertType]: next }));
    try {
      const confirmed = await setCaregiverAlertPreference(alertType, next);
      setEnabledByType((current) =>
        current === null ? current : { ...current, [alertType]: confirmed.enabled },
      );
    } catch (cause) {
      setEnabledByType((current) =>
        current === null ? current : { ...current, [alertType]: !next },
      );
      setSaveError(messageFor(cause));
    } finally {
      setSavingType(null);
    }
  };

  return (
    <>
      <h2>Updates you send to loved ones</h2>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          Choose which occasional updates the people you share with can receive. Everything is off
          until you turn it on. These are non-urgent nudges — not live monitoring, and not for
          emergencies. You can change or stop any of them at any time.
        </p>
        {saveError !== null && <ErrorNotice>{saveError}</ErrorNotice>}
        {error !== null && <ErrorNotice>{error}</ErrorNotice>}
        {loading && enabledByType === null && <Loading label="Loading your updates…" />}
        {enabledByType !== null &&
          ALERT_TYPE_ORDER.map((alertType) => (
            <PreferenceRow
              key={alertType}
              alertType={alertType}
              enabled={enabledByType[alertType] ?? false}
              disabled={savingType !== null}
              onToggle={(type, next) => {
                void toggle(type, next);
              }}
            />
          ))}
      </div>
    </>
  );
}
