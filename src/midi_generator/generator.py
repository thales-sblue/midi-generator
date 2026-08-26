"""Backward-compatible public helpers for melody generation."""

from pathlib import Path

from midi_generator.domain import MelodyRequest
from midi_generator.exporters import MidiExporter
from midi_generator.generation.melody import BEATS_PER_BAR, TICKS_PER_BEAT, generate_plan

GenerationConfig = MelodyRequest


def make_melody(config: MelodyRequest) -> list[tuple[int, int, int, int]]:
    """Return legacy (start, duration, pitch, velocity) note tuples."""
    return [(note.start, note.duration, note.pitch, note.velocity) for note in generate_plan(config).notes]


def generate_midi(config: MelodyRequest, destination: str | Path) -> Path:
    """Generate a MIDI file from the composition plan."""
    return MidiExporter().export(generate_plan(config), destination)
