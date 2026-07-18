"""Item administration seam (ADR-0043; roadmap Spec 4) — how symptom items are selected and
scored.

Today this is a **deterministic stub**, not adaptive testing: a fixed-order selector and a
sum-score estimator. The honesty guards make an overclaim structurally impossible:
`FixedOrderSelector.is_adaptive` and `SumScoreEstimator.is_irt` are both False, and the
estimator never touches item calibration, so a half-wired `ItemCalibration` cannot make a
sum score masquerade as an IRT ability estimate. Computerized Adaptive Testing (CAT) arrives
as a NEW selector/estimator behind this same seam, gated on `ItemBank.is_calibrated`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.psychometrics.item_bank import ItemBank


@dataclass(frozen=True, slots=True)
class FixedOrderSelector:
    """Presents the bank's items in their fixed declared order — NO adaptivity.

    A CAT selector (future) would pick the next item from the response so far and the item
    calibration; this one cannot, and says so via `is_adaptive`.
    """

    bank: ItemBank
    is_adaptive: bool = False

    def order(self) -> tuple[str, ...]:
        return self.bank.codes()


@dataclass(frozen=True, slots=True)
class SumScoreEstimator:
    """A deterministic raw sum score — NOT an IRT ability estimate.

    Intentionally ignores calibration entirely (`is_irt` is False), so it can never claim
    IRT precision. Responses are keyed by item code; unknown/extra keys are summed as given
    (the caller supplies only real item responses).
    """

    is_irt: bool = False

    def score(self, responses: Mapping[str, float]) -> float:
        return float(sum(responses.values()))
