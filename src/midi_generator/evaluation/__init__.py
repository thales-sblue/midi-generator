"""Deterministic candidate generation, objective scoring and ranking.

This is the evaluation/selection harness (architecture-audit gap #2) and the
repeatable instrument for the SkyTNT listening gate. It stays dependency-free and
reuses ``analysis.analyze_clip`` instead of an external metrics library.
"""

from .harness import (
    Backend,
    RankedCandidate,
    evaluate_request,
    generate_candidates,
    rank_candidates,
)
from .scoring import CandidateScore, plan_to_clip, score_plan, score_profile
from .seeds import derive_seeds

__all__ = [
    "Backend",
    "CandidateScore",
    "RankedCandidate",
    "derive_seeds",
    "evaluate_request",
    "generate_candidates",
    "plan_to_clip",
    "rank_candidates",
    "score_plan",
    "score_profile",
]
