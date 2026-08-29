"""Deterministic musical analysis for library-independent MIDI structures."""

from .clip_profile import ClipProfile, analyze_clip
from .scale_compatibility import ScaleCandidate, rank_scale_candidates

__all__ = [
    "ClipProfile",
    "ScaleCandidate",
    "analyze_clip",
    "rank_scale_candidates",
]
