"""AI narrative layer — validated, BAA-gated rephrasing of the computed trajectory
(ADR-0011).

The model never sees raw observations or ingested document text; it receives only the
computed Trajectory and may rephrase it. Its output is validated (no new numbers, no
direction contradiction, bounded length) and ANY failure falls back to the
deterministic template summary — AI absence can never break the endpoint.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any, Protocol

import httpx

from app.schemas.trajectory import Direction, Trajectory

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
REQUEST_TIMEOUT_S = 6.0  # narration is decorative; never let it drag the endpoint
MAX_NARRATIVE_CHARS = 360
MAX_OUTPUT_TOKENS = 200  # a 1-3 sentence rephrasing; shared across providers

_PROMPT = """\
You rewrite a health-trend summary for a patient in warm, plain language
(6th-8th grade). STRICT RULES:
- Use ONLY the facts below. Do not add numbers, measurements, causes, advice,
  diagnoses, or predictions that are not in the facts.
- Keep the overall direction exactly as stated. Never alarmist; for declines,
  gently suggest discussing with their care team.
- 1-3 short sentences, no lists, no links, no medical codes.
Reply with the rewritten summary only.

FACTS (computed by software, already verified):
{facts}
"""

# Output that contradicts the computed direction is rejected — UNLESS the term appears
# in the facts themselves (a declining trajectory may legitimately mention a bright-side
# signal that is "looking better"; review finding on mixed trajectories).
_CONTRADICTIONS: dict[Direction, tuple[str, ...]] = {
    Direction.improving: ("getting worse", "worse", "worsen", "declin", "deteriorat", "slipping"),
    Direction.declining: ("improving", "getting better", "looking better", "great news"),
    Direction.stable: ("getting worse", "worsen", "declin", "deteriorat", "getting better"),
    Direction.insufficient_data: (
        "improving",
        "getting better",
        "getting worse",
        "declin",
        "worsen",
    ),
}

# Digit-free assertions the model must never add: dosages, medication directives,
# causes, diagnoses (review finding: 'take 90 mg of gabapentin' passed the old check).
_ASSERTION_MARKERS = (
    " mg",
    " mcg",
    "milligram",
    "microgram",
    " dose",
    "dosag",
    "prescri",
    "medicat",
    "diagnos",
    "stop taking",
    "start taking",
    "increase your",
    "decrease your",
    "caused by",
    "because your",
    "recommend",
)

# Spelled-out numbers count as numbers (review finding: 'five hundred milligrams').
_NUMBER_WORDS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "thousand",
    "half",
)

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_RAW_CODE = re.compile(r"\b\d{1,7}-\d\b")  # LOINC-shaped codes never belong in prose
_WORD = re.compile(r"[a-z]+")


class Narrator(Protocol):
    """Turns a computed Trajectory into a friendlier summary, or None to fall back."""

    async def narrate(self, trajectory: Trajectory) -> str | None: ...


def _facts_for(trajectory: Trajectory) -> str:
    return json.dumps(
        {
            "direction": trajectory.direction.value,
            "current_summary": trajectory.summary,
            "signals": [
                {"trend": s.direction.value, "detail": s.detail} for s in trajectory.signals
            ],
            "data_gaps": trajectory.data_gaps,
        },
        ensure_ascii=False,
    )


def narrative_is_safe(text: str, trajectory: Trajectory, facts: str) -> bool:
    """The model may rephrase; it may not assert (ADR-0011 validation contract).

    Heuristic defense in depth — the prompt is the first line, this the second; the
    deterministic template is always the fallback, so a false rejection costs only
    warmth, never correctness.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_NARRATIVE_CHARS:
        return False
    lowered = stripped.lower()
    facts_lowered = facts.lower()
    if "http://" in lowered or "https://" in lowered:
        return False
    if _RAW_CODE.search(stripped):
        return False  # medical codes never belong in patient prose
    if any(marker in lowered for marker in _ASSERTION_MARKERS):
        return False  # dosage/directive/cause/diagnosis language is asserting
    if any(
        term in lowered and term not in facts_lowered
        for term in _CONTRADICTIONS[trajectory.direction]
    ):
        return False
    # Every number in the output — digits or words — must already exist in the facts.
    allowed = set(_NUMBER.findall(facts))
    if not all(number in allowed for number in _NUMBER.findall(stripped)):
        return False
    words = set(_WORD.findall(lowered))
    return not any(word in words and word not in facts_lowered for word in _NUMBER_WORDS)


class _HttpNarrator:
    """Shared narration flow for HTTP LLM providers (ADR-0011: BAA-gated by the caller).

    The flow is provider-independent: build the computed FACTS, send the one fixed
    prompt, then run the output through `narrative_is_safe`. Subclasses only implement
    `_complete` (the provider request/response shape). ANY exception — network, HTTP
    status, malformed body — falls back to None so the deterministic template always
    stands; narration can never break the endpoint. `_model` is the logical model label
    the caller uses for the cache key and the disclosure audit (never PHI).
    """

    def __init__(self, model: str, client: httpx.AsyncClient | None = None) -> None:
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S)

    async def _complete(self, prompt: str) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    async def narrate(self, trajectory: Trajectory) -> str | None:
        facts = _facts_for(trajectory)
        try:
            text = await self._complete(_PROMPT.format(facts=facts))
        except Exception:  # noqa: BLE001 — narration is decorative; ANY failure falls back
            return None
        return text.strip() if narrative_is_safe(text, trajectory, facts) else None

    async def aclose(self) -> None:
        await self._client.aclose()


class AnthropicNarrator(_HttpNarrator):
    """Narrator over the Anthropic Messages API (ADR-0011: BAA-gated by the caller)."""

    def __init__(self, api_key: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(model, client)
        self._api_key = api_key

    async def _complete(self, prompt: str) -> str:
        response = await self._client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return str(payload["content"][0]["text"])


class AzureOpenAINarrator(_HttpNarrator):
    """Narrator over an Azure OpenAI chat-completions deployment (ADR-0040).

    The HIPAA-eligible provider once Claude is off the PHI layer: Microsoft signs a BAA
    covering Azure OpenAI (still gated on the operator's `ai_baa_confirmed` attestation,
    exactly like the Anthropic path). Azure routes by DEPLOYMENT, not model id, and
    authenticates with an `api-key` header. `deployment` is used for the request URL and
    also passed up as `_model` so the cache key / disclosure audit label is stable and
    provider-neutral (set it to match `settings.ai_model`).
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        api_version: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(deployment, client)
        self._api_key = api_key
        self._url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={api_version}"
        )

    async def _complete(self, prompt: str) -> str:
        response = await self._client.post(
            self._url,
            headers={"api-key": self._api_key, "content-type": "application/json"},
            json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": MAX_OUTPUT_TOKENS,
                "temperature": 0.4,  # controlled rephrasing, not free generation
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return str(payload["choices"][0]["message"]["content"])


def narrative_cache_key(trajectory: Trajectory, model: str) -> str:
    """Stable key for one (facts, model) pair — identical trajectories share a
    narrative, so polling never repeats the provider call or the disclosure."""
    return hashlib.sha256(f"{model}|{_facts_for(trajectory)}".encode()).hexdigest()


class NarrativeCache:
    """Process-level narrative cache with FIFO eviction.

    Rejections are cached as None (negative cache): one provider call — one
    disclosure — per unique computed trajectory, never a retry loop on polling.
    `begin` marks a key in-flight so concurrent requests schedule only one narration.
    """

    def __init__(self, max_entries: int = 512) -> None:
        self._entries: OrderedDict[str, str | None] = OrderedDict()
        self._pending: set[str] = set()
        self._max = max_entries

    def lookup(self, key: str) -> tuple[bool, str | None]:
        """(known, narrative): known=True means an attempt already concluded."""
        if key in self._entries:
            return True, self._entries[key]
        return False, None

    def begin(self, key: str) -> bool:
        if key in self._entries or key in self._pending:
            return False
        self._pending.add(key)
        return True

    def finish(self, key: str, narrative: str | None) -> None:
        self._pending.discard(key)
        self._entries[key] = narrative
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        """Drop every cached narrative and in-flight marker.

        Account deletion (ADR-0027) invalidates through here: keys are content
        hashes of (facts, model), not patient ids, so one patient's entries cannot
        be purged selectively — the whole cache goes and repopulates on demand.
        """
        self._entries.clear()
        self._pending.clear()


NARRATIVE_CACHE = NarrativeCache()


def clear_narrative_cache() -> None:
    """Invalidate the process-level narrative cache — the seam account deletion
    (ADR-0027) calls so no narrative derived from a deleted patient's trajectory is
    served afterwards, without reaching into the cache's internals."""
    NARRATIVE_CACHE.clear()


async def narrate_into_cache(
    narrator: Narrator, trajectory: Trajectory, key: str, cache: NarrativeCache
) -> None:
    """Background job: call the provider and cache an accepted narrative.

    Runs AFTER the response is sent (FastAPI BackgroundTasks) so the LLM is never in
    the request path and never holds a DB transaction (standards.md; review finding).
    """
    try:
        narrative = await narrator.narrate(trajectory)
    except Exception:  # noqa: BLE001 — decorative; a failed narration must vanish quietly
        narrative = None
    cache.finish(key, narrative)
