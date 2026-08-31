"""Generate several candidate plans from one request and rank them objectively."""

from collections.abc import Callable
from dataclasses import dataclass, replace

from midi_generator.domain import CompositionPlan, MelodyRequest
from midi_generator.generation import generate_plan

from .scoring import CandidateScore, score_plan
from .seeds import derive_seeds

Backend = Callable[[MelodyRequest], CompositionPlan]


@dataclass(frozen=True)
class RankedCandidate:
    """One scored candidate together with its position in the ranking."""

    rank: int
    seed: int
    score: CandidateScore
    plan: CompositionPlan


def generate_candidates(
    request: MelodyRequest,
    count: int,
    *,
    backend: Backend = generate_plan,
) -> tuple[CompositionPlan, ...]:
    """Build ``count`` plans, one per seed derived from ``request.seed``.

    ``backend`` defaults to the heuristic generator; pass a one-argument
    callable (for example a closure over ``generate_contextual_plan`` and its
    reference clip) to evaluate another deterministic backend.
    """
    seeds = derive_seeds(request.seed, count)
    return tuple(backend(replace(request, seed=seed)) for seed in seeds)


def rank_candidates(
    plans: tuple[CompositionPlan, ...],
) -> tuple[RankedCandidate, ...]:
    """Rank plans by aggregate score, breaking ties by ascending seed."""
    scored = sorted(
        ((score_plan(plan), plan) for plan in plans),
        key=lambda item: (-item[0].aggregate, item[1].seed),
    )
    return tuple(
        RankedCandidate(
            rank=position, seed=plan.seed, score=score, plan=plan
        )
        for position, (score, plan) in enumerate(scored, start=1)
    )


def evaluate_request(
    request: MelodyRequest,
    count: int,
    *,
    backend: Backend = generate_plan,
) -> tuple[RankedCandidate, ...]:
    """Derive seeds, generate the candidates and return them ranked."""
    return rank_candidates(generate_candidates(request, count, backend=backend))
