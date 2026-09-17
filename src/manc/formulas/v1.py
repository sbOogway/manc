"""Formula v1: news sentiment, data surprise, event-risk shrink (blueprint section 5).

    N = Σ dᵢ·cᵢ·wᵢ·λᵢ / Σ cᵢ·wᵢ·λᵢ            λᵢ = 0.5^(ageᵢ / half_life)
    sₑ = clip((actual - consensus) / max(|consensus|, |previous|, ε), -1, 1) · sign(asset, event)
    S = Σ sₑ·impₑ / Σ impₑ                       imp: importance 1/2/3 → 0.25/0.5/1
    R = min(1, Σ_upcoming impₑ / event_risk_scale)
    score = 50 + 50·(news_weight·N + surprise_weight·S)·(1 - event_risk_shrink·R)

Every weight is a param; the defaults mirror config/scoring.yaml so empty params still score.
"""

from collections.abc import Mapping, Sequence

from .contract import AssetSpec, EventObservation, IndexScore, ScoringInputs, TaggedHeadline

DEFAULT_PARAMS: Mapping[str, float] = {
    "news_weight": 0.6,
    "surprise_weight": 0.4,
    "news_half_life_hours": 48.0,
    "event_risk_scale": 4.0,
    "event_risk_shrink": 0.5,
}
IMPORTANCE_WEIGHT = {1: 0.25, 2: 0.5, 3: 1.0}
EPSILON = 1e-9


class FormulaV1:
    name = "v1"

    def compute(self, inputs: ScoringInputs) -> IndexScore:
        params = {**DEFAULT_PARAMS, **inputs.params}
        news = _news_term(inputs.tags, inputs.as_of, params["news_half_life_hours"])
        surprise = _surprise_term(inputs.released, inputs.asset)
        risk = _event_risk(inputs.upcoming, params["event_risk_scale"])
        raw = params["news_weight"] * news + params["surprise_weight"] * surprise
        score = 50 + 50 * raw * (1 - params["event_risk_shrink"] * risk)
        return IndexScore(
            asset=inputs.asset.symbol,
            date=inputs.as_of.date(),
            score=min(100.0, max(0.0, score)),
            formula=self.name,
            components={"N": news, "S": surprise, "R": risk},
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


def _surprise_term(released: Sequence[EventObservation], asset: AssetSpec) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    for event in released:
        sign = asset.signs.get(event.country, {}).get(event.category, 0)
        if sign == 0 or event.actual is None or event.consensus is None:
            continue
        scale = max(abs(event.consensus), abs(event.previous or 0.0), EPSILON)
        surprise = min(1.0, max(-1.0, (event.actual - event.consensus) / scale))
        weight = IMPORTANCE_WEIGHT.get(event.importance, 0.25)
        weighted_sum += sign * surprise * weight
        weight_sum += weight
    return weighted_sum / weight_sum if weight_sum > 0 else 0.0


def _event_risk(upcoming: Sequence[EventObservation], scale: float) -> float:
    total = sum(IMPORTANCE_WEIGHT.get(event.importance, 0.25) for event in upcoming)
    return min(1.0, total / scale)
