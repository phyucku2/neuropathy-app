"""Symptom item-bank — single source of truth for the patient-reported symptom items
(ADR-0043; roadmap Spec 4).

Today the bank is **deterministic and uncalibrated**: it names the items, their polarity,
their honest measure-alignment, and their ADA construct mapping, but holds NO IRT
calibration (`ItemCalibration` fields are all None → `is_calibrated` is False). Nothing here
is a validated instrument and nothing may claim IRT while uncalibrated. Filling in
calibration is a gated data/validation step (Spec 4 open decisions), never inferred in code.

**Honesty note on the ADA mapping.** The ADA Standards of Care assess diabetic peripheral
neuropathy at diagnosis and at least annually (Rec 12.17), using clinician exam modalities:
temperature/pinprick for small-fiber, 128-Hz tuning-fork vibration for large-fiber, and an
annual 10-g monofilament (Rec 12.18; PMC10725803). OUR items are **patient-reported
symptoms**, not those clinician exams — so each item is mapped to the *fiber construct* the
ADA exam assesses (`ada_modality_related` = "related to", NOT "equivalent to"). This gives a
credible ADA-aligned frame without overstating that a self-report is a monofilament test.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ItemCalibration:
    """IRT calibration for one item. ALL None today — the bank is uncalibrated.

    `discrimination` (2PL/GRM slope) and `thresholds` (category boundaries) are placeholders
    to be filled ONLY from real calibration data; `model` names the fitted model once it
    exists. `is_calibrated` is the single guard consumers check before any IRT claim.
    """

    discrimination: float | None = None
    thresholds: tuple[float, ...] | None = None
    model: str | None = None

    @property
    def is_calibrated(self) -> bool:
        return self.discrimination is not None and self.thresholds is not None


@dataclass(frozen=True, slots=True)
class SymptomItem:
    """One patient-reported symptom item and its provenance/construct metadata.

    `polarity` is the string form of the shared better/worse polarity (must equal the
    directionality registry's `Polarity` for the same code — a parity test enforces it).
    `validated_instrument` stays False until a real validated instrument is licensed.
    """

    code: str
    display: str
    construct: str  # honest latent construct, e.g. "small_fiber_symptom"
    ada_fiber_class: str  # "small_fiber" | "large_fiber"
    # The ADA EXAM modality for this fiber class — "related to", NOT equivalent to.
    ada_modality_related: str
    measure_alignment: str  # "NRS-aligned" / "NTSS-6-aligned"
    polarity: str  # e.g. "lower_is_better" (higher raw = worse)
    scale_min: int
    scale_max: int
    validated_instrument: bool = False
    calibration: ItemCalibration = field(default_factory=ItemCalibration)


@dataclass(frozen=True, slots=True)
class ItemBank:
    """An ordered, versioned set of symptom items with a shared instrument identity."""

    instrument: str
    instrument_version: str
    ada_reference: str
    items: tuple[SymptomItem, ...]

    def codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.items)

    def get(self, code: str) -> SymptomItem | None:
        return next((item for item in self.items if item.code == code), None)

    @property
    def is_calibrated(self) -> bool:
        """True only if EVERY item carries real calibration. False today (uncalibrated)."""
        return bool(self.items) and all(item.calibration.is_calibrated for item in self.items)


# The concrete bank. Values MUST match what app/ingestion/adl.py emitted before the refactor
# (instrument "symptom-check-in" v1, 0-10, lower_is_better, aligned-not-validated) — the
# emitted Observations stay byte-identical, with the ADA construct keys added additively.
SYMPTOM_ITEM_BANK = ItemBank(
    instrument="symptom-check-in",
    instrument_version="1",
    ada_reference="ADA Standards of Care Rec 12.17 (>= annual assessment) / 12.18 (modalities)",
    items=(
        SymptomItem(
            code="symptom_pain",
            display="Pain",
            construct="small_fiber_symptom",
            ada_fiber_class="small_fiber",
            ada_modality_related="temperature/pinprick",
            measure_alignment="NRS-aligned",  # 0-10 Numeric Rating Scale (public-domain)
            polarity="lower_is_better",
            scale_min=0,
            scale_max=10,
        ),
        SymptomItem(
            code="symptom_numbness",
            display="Numbness or tingling",
            # Numbness/loss-of-sensation is a large-fiber symptom (the item wording also
            # names tingling, a mixed/positive symptom — kept honest in the ADR).
            construct="large_fiber_symptom",
            ada_fiber_class="large_fiber",
            ada_modality_related="128-Hz vibration / 10-g monofilament",
            measure_alignment="NTSS-6-aligned",  # numbness/paresthesia severity item
            polarity="lower_is_better",
            scale_min=0,
            scale_max=10,
        ),
    ),
)
