"""Formula v1: news sentiment, data surprise, event-risk shrink (blueprint section 5).

M1 stub: returns the neutral score. The real computation lands in M3.
"""

from .contract import IndexScore, ScoringInputs


class FormulaV1:
    name = "v1"

    def compute(self, inputs: ScoringInputs) -> IndexScore:
        return IndexScore(
            asset=inputs.asset.symbol,
            date=inputs.as_of.date(),
            score=50.0,
            formula=self.name,
            components={},
            n_news=len(inputs.tags),
            n_events=len(inputs.released),
        )
