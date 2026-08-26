"""Deterministic MIDI melody generator."""

from .domain import CompositionPlan, GenerationReport, MelodyRequest, NoteEvent
from .generator import GenerationConfig, generate_midi, make_melody

__all__ = [
    "CompositionPlan", "GenerationConfig", "GenerationReport", "MelodyRequest",
    "NoteEvent", "generate_midi", "make_melody",
]
