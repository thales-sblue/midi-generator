"""Musical composition algorithms."""

from .accompaniment import (
    DRUM_STYLES,
    Accompaniment,
    accompaniment_tempo_map,
    analysis_request,
    generate_accompaniment,
    generate_bass_from_analysis,
    generate_drums_from_analysis,
    harmonic_reference_clip,
)
from .bass_line import generate_bass_line_plan
from .chords import generate_chord_bed_plan
from .contextual import generate_contextual_plan
from .drums import generate_hihat_plan, generate_kick_plan, generate_snare_plan
from .melody import generate_plan

__all__ = [
    "DRUM_STYLES",
    "Accompaniment",
    "accompaniment_tempo_map",
    "analysis_request",
    "generate_accompaniment",
    "generate_bass_from_analysis",
    "generate_drums_from_analysis",
    "harmonic_reference_clip",
    "generate_bass_line_plan",
    "generate_chord_bed_plan",
    "generate_contextual_plan",
    "generate_hihat_plan",
    "generate_kick_plan",
    "generate_plan",
    "generate_snare_plan",
]
