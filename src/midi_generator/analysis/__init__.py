"""Deterministic musical analysis for library-independent MIDI structures."""

from .clip_profile import (
    ClipProfile,
    analyze_clip,
    bass_line_pitches,
    top_line_intervals,
)
from .scale_compatibility import ScaleCandidate, rank_scale_candidates

__all__ = [
    "ClipProfile",
    "ScaleCandidate",
    "analyze_clip",
    "bass_line_pitches",
    "rank_scale_candidates",
    "top_line_intervals",
]
