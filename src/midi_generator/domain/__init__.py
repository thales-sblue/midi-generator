"""Domain models independent of MIDI file libraries."""

from .composition_plan import CompositionPlan
from .generation_report import GenerationReport
from .music_theory import (
    nearest_scale_pitch,
    scale_pitch_classes,
    scale_pitches,
)
from .note_event import NoteEvent
from .requests import MelodyRequest
from .time_signature import TimeSignature

__all__ = [
    "CompositionPlan",
    "GenerationReport",
    "MelodyRequest",
    "NoteEvent",
    "TimeSignature",
    "nearest_scale_pitch",
    "scale_pitch_classes",
    "scale_pitches",
]
