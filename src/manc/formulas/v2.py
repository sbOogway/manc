"""Formula v2: v1's terms on a -100..100 scale, plus the M6 candidates as switches.

    R as in v1
    N = Σ dᵢ·ĉᵢ·wᵢ·λᵢ·νᵢ / Σ ĉᵢ·wᵢ·λᵢ·νᵢ        ĉᵢ = ceil(cᵢ·levels)/levels (coarse confidence);
                                                 νᵢ = decay^(k-1) for the k-th strongest copy
                                                 of a story within 24h, same direction
                                                 (novelty weighting)
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

import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
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
    "novelty_weighting": 1,
    "novelty_decay": 0.75,
    "novelty_window_hours": 24.0,
    "novelty_similarity": 0.5,
    "coarse_confidence": 1,
    "confidence_levels": 3,
}
_SOURCE_SUFFIX = re.compile(r"\s+[-|\u2013\u2014]\s+[^-|\u2013\u2014]+$")  # "... - Reuters"
_WORD = re.compile(r"[a-z0-9]{3,}")
IMPORTANCE_WEIGHT = {1: 0.25, 2: 0.5, 3: 1.0}
EPSILON = 1e-9


class FormulaV2:
    name = "v2"
    scale = Scale(low=-100.0, high=100.0, neutral=0.0, edges=(-40.0, -10.0, 10.0, 40.0))
    windows: Mapping[str, int] = {"released_days": 90}  # the decayed surprise looks further back

    def compute(self, inputs: ScoringInputs) -> IndexScore:
        params = {**DEFAULT_PARAMS, **inputs.params}
        tags = _coarsen(inputs.tags, params)
        news = _news_term(tags, inputs.as_of, params)
        surprise = _surprise_term(inputs.released, inputs.asset, inputs.as_of, params)
        risk = _event_risk(inputs.upcoming, params["event_risk_scale"])
        dispersion = _dispersion(tags)
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


def _bucket(confidence: float, levels: int = 3) -> float:
    """Coarse confidence: the smallest of `levels` equal steps at or above the value."""
    return math.ceil(confidence * levels - 1e-9) / levels if confidence > 0 else 0.0


def _coarsen(tags: Sequence[TaggedHeadline], params: Mapping[str, float]) -> list[TaggedHeadline]:
    if not params["coarse_confidence"]:
        return list(tags)
    levels = int(params["confidence_levels"])
    return [
        TaggedHeadline(
            direction=tag.direction,
            confidence=_bucket(tag.confidence, levels),
            source_weight=tag.source_weight,
            published_at=tag.published_at,
            title=tag.title,
        )
        for tag in tags
    ]


def _news_term(tags: Sequence[TaggedHeadline], as_of, params: Mapping[str, float]) -> float:
    half_life_hours = params["news_half_life_hours"]
    novelty = _novelty(tags, params) if params["novelty_weighting"] else [1.0] * len(tags)
    weighted_sum = 0.0
    weight_sum = 0.0
    for tag, freshness in zip(tags, novelty, strict=True):
        age_hours = max(0.0, (as_of - tag.published_at).total_seconds() / 3600)
        decay = 0.5 ** (age_hours / half_life_hours)
        weight = tag.confidence * tag.source_weight * decay * freshness
        weighted_sum += tag.direction * weight
        weight_sum += weight
    return weighted_sum / weight_sum if weight_sum > 0 else 0.0


def _tokens(title: str) -> frozenset[str]:
    return frozenset(_WORD.findall(_SOURCE_SUFFIX.sub("", title.lower())))


def _novelty(tags: Sequence[TaggedHeadline], params: Mapping[str, float]) -> list[float]:
    """Per tag, decay^(k-1) where k is its rank inside its cluster of near-duplicate titles.

    Clusters are formed within one direction, strongest copy first (confidence times source
    weight), so adding a headline never lowers the weight its own side already had.
    """
    window = timedelta(hours=params["novelty_window_hours"])
    threshold = params["novelty_similarity"]
    decay = params["novelty_decay"]
    novelty = [1.0] * len(tags)
    for direction in (-1, 0, 1):
        members = [index for index, tag in enumerate(tags) if tag.direction == direction]
        members.sort(
            key=lambda index: (
                -tags[index].confidence * tags[index].source_weight,
                tags[index].published_at,
            )
        )
        clusters: list[tuple[frozenset[str], datetime, int]] = []  # tokens, lead time, size
        for index in members:
            tokens = _tokens(tags[index].title)
            if not tokens:
                continue
            for position, (lead_tokens, lead_time, size) in enumerate(clusters):
                within = abs(tags[index].published_at - lead_time) <= window
                overlap = len(tokens & lead_tokens) / len(tokens | lead_tokens)
                if within and overlap >= threshold:
                    novelty[index] = decay**size
                    clusters[position] = (lead_tokens, lead_time, size + 1)
                    break
            else:
                clusters.append((tokens, tags[index].published_at, 1))
    return novelty


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
