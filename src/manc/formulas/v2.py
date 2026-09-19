"""Formula v2: v1's terms on a -100..100 scale, plus the M6 candidates as switches.

    N, R as in v1
    sₑ = clip(zₑ / z_cap, -1, 1) · sign        zₑ = (actual - consensus) / σₑ, σₑ from the
                                                 release's past surprises; the v1 normaliser
                                                 below min_history or when σₑ = 0
    S = Σ sₑ·impₑ·δₑ / Σ impₑ·δₑ                δₑ = 0.5^(age_days / half_life_days) over a
                                                 90-day window
    D = std(dᵢ·cᵢ)                              stored, not scored
    score = 100·(news_weight·N + surprise_weight·S)·(1 - event_risk_shrink·R)

Bands sit at ±10 and ±40, the same proportions as v1's 45/55 and 30/70. Each candidate is a
`params` switch (1 on, 0 off) so any subset can be replayed (blueprint section 9, M6).
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from statistics import pstdev

from .contract import (
    AssetSpec,
    EventObservation,
    IndexScore,
    Scale,
    ScoringInputs,
    TaggedHeadline,
)

DEFAULT_PARAMS: Mapping[str, float] = {
    "news_weight": 0.6,
    "surprise_weight": 0.4,
    "news_half_life_hours": 48.0,
    "event_risk_scale": 4.0,
    "event_risk_shrink": 0.5,
    "standardised_surprise": 1,
    "surprise_min_history": 8,
    "surprise_z_cap": 2.0,
    "decayed_surprise": 1,
    "surprise_half_life_days": 14.0,
}
IMPORTANCE_WEIGHT = {1: 0.25, 2: 0.5, 3: 1.0}
EPSILON = 1e-9


class FormulaV2:
    name = "v2"
    scale = Scale(low=-100.0, high=100.0, neutral=0.0, edges=(-40.0, -10.0, 10.0, 40.0))
    windows: Mapping[str, int] = {"released_days": 90}  # the decayed surprise looks further back

    def compute(self, inputs: ScoringInputs) -> IndexScore:
        params = {**DEFAULT_PARAMS, **inputs.params}
        news = _news_term(inputs.tags, inputs.as_of, params["news_half_life_hours"])
        surprise = _surprise_term(inputs.released, inputs.asset, inputs.as_of, params)
        risk = _event_risk(inputs.upcoming, params["event_risk_scale"])
        dispersion = _dispersion(inputs.tags)
        raw = params["news_weight"] * news + params["surprise_weight"] * surprise
        score = 100 * raw * (1 - params["event_risk_shrink"] * risk)
        return IndexScore(
            asset=inputs.asset.symbol,
            date=inputs.as_of.date(),
            score=self.scale.clip(score),
            formula=self.name,
            components={"N": news, "S": surprise, "R": risk, "D": dispersion},
            n_news=len(inputs.tags),
            n_events=len(inputs.released),
        )


def _news_term(tags: Sequence[TaggedHeadline], as_of, half_life_hours: float) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    for tag in tags:
        age_hours = max(0.0, (as_of - tag.published_at).total_seconds() / 3600)
        weight = tag.confidence * tag.source_weight * 0.5 ** (age_hours / half_life_hours)
        weighted_sum += tag.direction * weight
        weight_sum += weight
    return weighted_sum / weight_sum if weight_sum > 0 else 0.0


def _dispersion(tags: Sequence[TaggedHeadline]) -> float:
    """How much the tags disagree: the spread of dᵢ·cᵢ, 0 when unanimous or empty."""
    if len(tags) < 2:
        return 0.0
    return pstdev(tag.direction * tag.confidence for tag in tags)


def _surprise_term(
    released: Sequence[EventObservation],
    asset: AssetSpec,
    as_of: datetime,
    params: Mapping[str, float],
) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    for event in released:
        sign = asset.signs.get(event.country, {}).get(event.category, 0)
        if sign == 0 or event.actual is None or event.consensus is None:
            continue
        surprise = _surprise(event, params)
        weight = IMPORTANCE_WEIGHT.get(event.importance, 0.25)
        if params["decayed_surprise"]:
            age_days = max(0.0, (as_of - event.date).total_seconds() / 86400)
            weight *= 0.5 ** (age_days / params["surprise_half_life_days"])
        weighted_sum += sign * surprise * weight
        weight_sum += weight
    return weighted_sum / weight_sum if weight_sum > 0 else 0.0


def _surprise(event: EventObservation, params: Mapping[str, float]) -> float:
    """The release's surprise in -1..1: standardised on its own history when there is enough."""
    assert event.actual is not None and event.consensus is not None
    raw = event.actual - event.consensus
    if (
        params["standardised_surprise"]
        and len(event.past_surprises) >= params["surprise_min_history"]
    ):
        sigma = pstdev(event.past_surprises)
        if sigma > 0:
            return min(1.0, max(-1.0, raw / sigma / params["surprise_z_cap"]))
    scale = max(abs(event.consensus), abs(event.previous or 0.0), EPSILON)
    return min(1.0, max(-1.0, raw / scale))


def _event_risk(upcoming: Sequence[EventObservation], scale: float) -> float:
    total = sum(IMPORTANCE_WEIGHT.get(event.importance, 0.25) for event in upcoming)
    return min(1.0, total / scale)
