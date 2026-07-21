"""Unit tests for the caregiver-alert engine (ADR-0047 Phase B1): the scope gate, each
compute-on-read evaluator's dedupe-key logic, and the full
scope x type x preference x link-status matrix — proving a trends-only caregiver never
sees (or can acknowledge, or learns the existence of) a med_change / new_chart_note
alert. All data is synthetic (CLAUDE.md §5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.caregiver import (
    CaregiverAlertType,
    CaregiverLink,
    CaregiverLinkStatus,
    CaregiverScope,
)
from app.models.connection import Initiator
from app.models.emr_clinical_note import EmrClinicalNote
from app.models.observation import DataOrigin, Observation, ObservationStatus, SourceType
from app.models.user import UserRole
from app.repositories.caregiver_alert import InMemoryCaregiverAlertRepository
from app.repositories.user import UserRecord
from app.services.caregiver import CaregiverService
from app.services.caregiver_alert import CaregiverAlertService, type_allowed_for_scope

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


def _build() -> CaregiverAlertService:
    caregivers = CaregiverService()
    return CaregiverAlertService(
        caregivers=caregivers,
        alerts=InMemoryCaregiverAlertRepository(links=caregivers.links),
    )


async def _linked(
    service: CaregiverAlertService,
    *,
    scope: CaregiverScope = CaregiverScope.full,
    status: CaregiverLinkStatus = CaregiverLinkStatus.active,
    accepted: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, CaregiverLink]:
    """Seed a caregiver user, a patient user, and a link at the given scope/status.
    Returns (caregiver_user_id, patient_id, link)."""
    caregiver_user_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    await service.caregivers.users.add(
        UserRecord(
            id=caregiver_user_id,
            email=f"care-{caregiver_user_id.hex[:8]}@example.com",
            password_hash="x",
            display_name="Cam Caregiver",
            role=UserRole.caregiver,
            patient_id=None,
        )
    )
    await service.caregivers.users.add(
        UserRecord(
            id=uuid.uuid4(),
            email=f"pat-{patient_id.hex[:8]}@example.com",
            password_hash="x",
            display_name="Pat Patient",
            role=UserRole.patient,
            patient_id=patient_id,
        )
    )
    link = await service.caregivers.links.add(
        CaregiverLink(
            patient_id=patient_id,
            caregiver_user_id=caregiver_user_id,
            scope=scope,
            status=status,
            initiated_by=Initiator.patient,
            accepted_at=NOW if accepted else None,
        )
    )
    return caregiver_user_id, patient_id, link


async def _enable_all(service: CaregiverAlertService, patient_id: uuid.UUID) -> None:
    for alert_type in CaregiverAlertType:
        await service.preferences.upsert(patient_id=patient_id, alert_type=alert_type, enabled=True)


def _adl(patient_id: uuid.UUID, days_ago: float) -> Observation:
    return Observation(
        patient_id=patient_id,
        source=SourceType.adl,
        origin=DataOrigin.patient_reported,
        code="adl_katz",
        value_num=6.0,
        effective_at=NOW - timedelta(days=days_ago),
        recorded_at=NOW - timedelta(days=days_ago),
        status=ObservationStatus.final,
        quality={},
        payload={},
    )


def _med(patient_id: uuid.UUID, days_ago: float) -> Observation:
    return Observation(
        id=uuid.uuid4(),
        patient_id=patient_id,
        source=SourceType.medication,
        origin=DataOrigin.patient_reported,
        code=f"med:{uuid.uuid4()}",
        value_num=1.0,
        effective_at=NOW - timedelta(days=days_ago),
        recorded_at=NOW - timedelta(days=days_ago),
        status=ObservationStatus.final,
        quality={},
        payload={},
    )


def _note(patient_id: uuid.UUID, import_key: str, days_ago: float) -> EmrClinicalNote:
    return EmrClinicalNote(
        patient_id=patient_id,
        connection_id=uuid.uuid4(),
        authored_at=NOW - timedelta(days=days_ago),
        import_key=import_key,
    )


async def _seed_improving_labs(service: CaregiverAlertService, patient_id: uuid.UUID) -> None:
    # hba1c falling = improving trajectory -> a MOVING signal for code 4548-4.
    for value, days_ago in ((9.0, 90), (8.3, 60), (7.6, 30), (7.0, 5)):
        service_obs = Observation(
            patient_id=patient_id,
            source=SourceType.lab,
            origin=DataOrigin.ehr_imported,
            code="4548-4",
            value_num=value,
            effective_at=NOW - timedelta(days=days_ago),
            recorded_at=NOW - timedelta(days=days_ago),
            status=ObservationStatus.final,
            quality={},
            payload={},
        )
        await service.observations.add(service_obs)


# ---------------------------------------------------------------- the scope gate


def test_scope_matrix_trends_allows_only_two_types() -> None:
    allowed = {t for t in CaregiverAlertType if type_allowed_for_scope(t, CaregiverScope.trends)}
    assert allowed == {CaregiverAlertType.missed_checkin, CaregiverAlertType.trend_shift}


def test_scope_matrix_full_allows_all_four_types() -> None:
    allowed = {t for t in CaregiverAlertType if type_allowed_for_scope(t, CaregiverScope.full)}
    assert allowed == set(CaregiverAlertType)


# ---------------------------------------------------------------- evaluators


async def test_missed_checkin_fires_only_when_no_recent_adl() -> None:
    service = _build()
    _, patient_id, _ = await _linked(service)
    # No ADL at all -> one missed-window date key.
    keys = await service._eval_missed_checkin(patient_id, now=NOW)
    assert keys == [NOW.date().isoformat()]
    # A fresh check-in inside the window -> no alert.
    await service.observations.add(_adl(patient_id, days_ago=1))
    assert await service._eval_missed_checkin(patient_id, now=NOW) == []
    # An old check-in (>7d) does NOT count -> alert again.
    service2 = _build()
    _, patient2, _ = await _linked(service2)
    await service2.observations.add(_adl(patient2, days_ago=9))
    assert await service2._eval_missed_checkin(patient2, now=NOW) == [NOW.date().isoformat()]


async def test_med_change_dedupe_key_is_the_observation_id() -> None:
    service = _build()
    _, patient_id, _ = await _linked(service)
    med_a = _med(patient_id, days_ago=2)
    med_b = _med(patient_id, days_ago=1)
    await service.observations.add(med_a)
    await service.observations.add(med_b)
    keys = await service._eval_med_change(patient_id, now=NOW, since=NOW - timedelta(days=30))
    assert set(keys) == {str(med_a.id), str(med_b.id)}


async def test_trend_shift_dedupe_key_is_code_plus_iso_week() -> None:
    service = _build()
    _, patient_id, _ = await _linked(service)
    await _seed_improving_labs(service, patient_id)
    keys = await service._eval_trend_shift(patient_id, now=NOW)
    iso = NOW.isocalendar()
    assert keys == [f"4548-4:{iso.year}-W{iso.week:02d}"]
    # A patient with no moving signal yields nothing.
    service2 = _build()
    _, patient2, _ = await _linked(service2)
    assert await service2._eval_trend_shift(patient2, now=NOW) == []


async def test_new_chart_note_dedupe_key_is_the_import_key() -> None:
    service = _build()
    _, patient_id, _ = await _linked(service)
    await service.clinical_notes.add_if_absent(_note(patient_id, "doc-1", days_ago=2))
    await service.clinical_notes.add_if_absent(_note(patient_id, "doc-2", days_ago=1))
    keys = await service._eval_new_chart_note(patient_id, now=NOW, since=NOW - timedelta(days=30))
    assert set(keys) == {"doc-1", "doc-2"}


async def test_new_chart_note_skips_notes_without_import_key() -> None:
    service = _build()
    _, patient_id, _ = await _linked(service)
    await service.clinical_notes.add_if_absent(_note(patient_id, "doc-1", days_ago=1))
    # A keyless note has no stable identity to dedupe on -> not a candidate.
    keyless = EmrClinicalNote(
        patient_id=patient_id, connection_id=uuid.uuid4(), authored_at=NOW, import_key=None
    )
    await service.clinical_notes.add_if_absent(keyless)
    keys = await service._eval_new_chart_note(patient_id, now=NOW, since=NOW - timedelta(days=30))
    assert keys == ["doc-1"]


# ---------------------------------------------------------------- dedupe on feed


async def test_two_feed_reads_produce_one_row_per_event() -> None:
    service = _build()
    caregiver_id, patient_id, link = await _linked(service)
    await _enable_all(service, patient_id)
    med = _med(patient_id, days_ago=1)
    await service.observations.add(med)

    first = await service.feed_for_caregiver(caregiver_id, now=NOW)
    med_alerts = [a for a, _ in first if a.alert_type is CaregiverAlertType.med_change]
    assert len(med_alerts) == 1
    # A second read re-runs the evaluator; add_if_absent dedupes -> still ONE row.
    second = await service.feed_for_caregiver(caregiver_id, now=NOW)
    med_alerts_2 = [a for a, _ in second if a.alert_type is CaregiverAlertType.med_change]
    assert len(med_alerts_2) == 1
    assert med_alerts_2[0].id == med_alerts[0].id


async def test_retry_shape_new_chart_note_dedupes_on_import_key() -> None:
    service = _build()
    caregiver_id, patient_id, _ = await _linked(service)
    await _enable_all(service, patient_id)
    # Same import_key, different row id (a rolled-back import that retried).
    await service.clinical_notes.add_if_absent(_note(patient_id, "doc-1", days_ago=1))
    await service.feed_for_caregiver(caregiver_id, now=NOW)
    # A second note row carrying the SAME import_key must not create a second alert.
    retried = EmrClinicalNote(
        id=uuid.uuid4(),
        patient_id=patient_id,
        connection_id=uuid.uuid4(),
        authored_at=NOW,
        import_key="doc-1",
    )
    # add_if_absent on the NOTE store dedupes it too, but even if it landed the alert
    # dedupes on the shared import_key -> one alert row.
    await service.clinical_notes.add_if_absent(retried)
    feed = await service.feed_for_caregiver(caregiver_id, now=NOW)
    note_alerts = [a for a, _ in feed if a.alert_type is CaregiverAlertType.new_chart_note]
    assert len(note_alerts) == 1


# ---------------------------------------------------------------- the full matrix


async def test_trends_scope_never_surfaces_med_or_note_alerts() -> None:
    service = _build()
    caregiver_id, patient_id, link = await _linked(service, scope=CaregiverScope.trends)
    await _enable_all(service, patient_id)  # every type opted in
    # Seed data for ALL four evaluators.
    await service.observations.add(_med(patient_id, days_ago=1))
    await service.clinical_notes.add_if_absent(_note(patient_id, "doc-1", days_ago=1))
    await _seed_improving_labs(service, patient_id)

    feed = await service.feed_for_caregiver(caregiver_id, now=NOW)
    types = {a.alert_type for a, _ in feed}
    # trends: only the two allowed types can ever appear — no med_change/new_chart_note.
    assert CaregiverAlertType.med_change not in types
    assert CaregiverAlertType.new_chart_note not in types
    assert types <= {CaregiverAlertType.missed_checkin, CaregiverAlertType.trend_shift}
    # And no med/note alert ROW was even persisted (existence must not leak).
    all_rows = await service.alerts.list_for_link(link.id)
    persisted_types = {a.alert_type for a in all_rows}
    assert CaregiverAlertType.med_change not in persisted_types
    assert CaregiverAlertType.new_chart_note not in persisted_types


async def test_full_scope_surfaces_all_opted_in_types() -> None:
    service = _build()
    caregiver_id, patient_id, _ = await _linked(service, scope=CaregiverScope.full)
    await _enable_all(service, patient_id)
    await service.observations.add(_med(patient_id, days_ago=1))
    await service.clinical_notes.add_if_absent(_note(patient_id, "doc-1", days_ago=1))
    await _seed_improving_labs(service, patient_id)

    feed = await service.feed_for_caregiver(caregiver_id, now=NOW)
    types = {a.alert_type for a, _ in feed}
    assert types == set(CaregiverAlertType)


async def test_preference_off_suppresses_the_type_even_at_full_scope() -> None:
    service = _build()
    caregiver_id, patient_id, _ = await _linked(service, scope=CaregiverScope.full)
    # Only missed_checkin opted in; everything else DEFAULT OFF.
    await service.preferences.upsert(
        patient_id=patient_id, alert_type=CaregiverAlertType.missed_checkin, enabled=True
    )
    await service.observations.add(_med(patient_id, days_ago=1))
    await _seed_improving_labs(service, patient_id)

    feed = await service.feed_for_caregiver(caregiver_id, now=NOW)
    types = {a.alert_type for a, _ in feed}
    assert types == {CaregiverAlertType.missed_checkin}


async def test_pending_link_yields_no_feed_and_no_alerts() -> None:
    service = _build()
    caregiver_id, patient_id, _ = await _linked(
        service, status=CaregiverLinkStatus.pending, accepted=False
    )
    await _enable_all(service, patient_id)
    await service.observations.add(_med(patient_id, days_ago=1))
    # Not accepted -> patients_for_caregiver returns nothing -> no evaluators run.
    feed = await service.feed_for_caregiver(caregiver_id, now=NOW)
    assert feed == []


async def test_revoked_link_yields_no_feed() -> None:
    service = _build()
    caregiver_id, patient_id, _ = await _linked(
        service, status=CaregiverLinkStatus.revoked, accepted=True
    )
    await _enable_all(service, patient_id)
    await service.observations.add(_med(patient_id, days_ago=1))
    assert await service.feed_for_caregiver(caregiver_id, now=NOW) == []


async def test_scope_downgrade_hides_prior_alerts_on_reread() -> None:
    service = _build()
    caregiver_id, patient_id, link = await _linked(service, scope=CaregiverScope.full)
    await _enable_all(service, patient_id)
    await service.observations.add(_med(patient_id, days_ago=1))
    first = await service.feed_for_caregiver(caregiver_id, now=NOW)
    assert any(a.alert_type is CaregiverAlertType.med_change for a, _ in first)

    # Patient narrows the link to trends AFTER the med_change alert was written.
    link.scope = CaregiverScope.trends
    await service.caregivers.links.update(link)
    second = await service.feed_for_caregiver(caregiver_id, now=NOW)
    assert not any(a.alert_type is CaregiverAlertType.med_change for a, _ in second)


# ---------------------------------------------------------------- ack authorization


async def test_ack_unknown_alert_is_none() -> None:
    service = _build()
    caregiver_id, _, _ = await _linked(service)
    assert (
        await service.acknowledge(caregiver_user_id=caregiver_id, alert_id=uuid.uuid4(), now=NOW)
        is None
    )


async def test_ack_marks_and_is_idempotent_with_single_audit() -> None:
    service = _build()
    caregiver_id, patient_id, _ = await _linked(service)
    await _enable_all(service, patient_id)
    await service.observations.add(_med(patient_id, days_ago=1))
    feed = await service.feed_for_caregiver(caregiver_id, now=NOW)
    alert = next(a for a, _ in feed if a.alert_type is CaregiverAlertType.med_change)

    first = await service.acknowledge(caregiver_user_id=caregiver_id, alert_id=alert.id, now=NOW)
    assert first is True
    # Double-ack: quiet success, no second audit event.
    second = await service.acknowledge(caregiver_user_id=caregiver_id, alert_id=alert.id, now=NOW)
    assert second is False
    ack_events = [
        e
        for e in service.audit._events  # type: ignore[attr-defined]
        if e.action == "caregiver_alert_ack"
    ]
    assert len(ack_events) == 1


async def test_trends_caregiver_cannot_ack_a_med_alert_from_another_link() -> None:
    """A med_change alert exists (written under a full-scope link). A DIFFERENT
    trends-only caregiver on the same patient must get None (404) — existence must not
    leak, and scope must not be bypassable via a known alert id."""
    service = _build()
    # Full-scope caregiver creates the med alert.
    full_cid, patient_id, _ = await _linked(service, scope=CaregiverScope.full)
    await _enable_all(service, patient_id)
    await service.observations.add(_med(patient_id, days_ago=1))
    feed = await service.feed_for_caregiver(full_cid, now=NOW)
    med_alert = next(a for a, _ in feed if a.alert_type is CaregiverAlertType.med_change)

    # A second, trends-only caregiver linked to the SAME patient.
    trends_cid = uuid.uuid4()
    await service.caregivers.users.add(
        UserRecord(
            id=trends_cid,
            email="trends@example.com",
            password_hash="x",
            display_name="Trends Only",
            role=UserRole.caregiver,
            patient_id=None,
        )
    )
    await service.caregivers.links.add(
        CaregiverLink(
            patient_id=patient_id,
            caregiver_user_id=trends_cid,
            scope=CaregiverScope.trends,
            status=CaregiverLinkStatus.active,
            initiated_by=Initiator.patient,
            accepted_at=NOW,
        )
    )
    # The alert is not this caregiver's link AND its type is out of trends scope -> None.
    assert (
        await service.acknowledge(caregiver_user_id=trends_cid, alert_id=med_alert.id, now=NOW)
        is None
    )


# ---------------------------------------------------------------- preferences


async def test_list_preferences_defaults_all_off() -> None:
    service = _build()
    _, patient_id, _ = await _linked(service)
    prefs = dict(await service.list_preferences(patient_id))
    assert set(prefs) == set(CaregiverAlertType)
    assert all(enabled is False for enabled in prefs.values())


async def test_set_preference_audits_only_on_change() -> None:
    service = _build()
    _, patient_id, _ = await _linked(service)
    actor = uuid.uuid4()
    assert (
        await service.set_preference(
            patient_id=patient_id,
            actor_id=actor,
            alert_type=CaregiverAlertType.trend_shift,
            enabled=True,
            now=NOW,
        )
        is True
    )
    # No-change write: quiet success, no second audit.
    assert (
        await service.set_preference(
            patient_id=patient_id,
            actor_id=actor,
            alert_type=CaregiverAlertType.trend_shift,
            enabled=True,
            now=NOW,
        )
        is True
    )
    pref_events = [
        e
        for e in service.audit._events  # type: ignore[attr-defined]
        if e.action == "set_caregiver_alert_preference"
    ]
    assert len(pref_events) == 1
    assert pref_events[0].detail == {"alert_type": "trend_shift", "enabled": True}
