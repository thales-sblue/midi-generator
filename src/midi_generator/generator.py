"""Core deterministic melody-generation logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

TICKS_PER_BEAT = 480
BEATS_PER_BAR = 4
STEP_TICKS = TICKS_PER_BEAT // 2  # eighth-note grid

ROOT_NOTES = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
    "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
    "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}
SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),  # natural minor
}


@dataclass(frozen=True)
class GenerationConfig:
    bpm: int
    root_note: str
    scale: str
    bars: int
    seed: int

    def validate(self) -> None:
        if not 20 <= self.bpm <= 400:
            raise ValueError("BPM must be between 20 and 400.")
        if self.root_note.upper() not in ROOT_NOTES:
            raise ValueError("Root note must be one of C, C#, Db, D, etc.")
        if self.scale.lower() not in SCALE_INTERVALS:
            raise ValueError("Scale must be 'major' or 'minor'.")
        if self.bars < 1:
            raise ValueError("Bars must be at least 1.")


def scale_notes(root_note: str, scale: str) -> tuple[int, ...]:
    """Return scale MIDI pitches across two octaves, starting at C4 range."""
    root = 60 + ROOT_NOTES[root_note.upper()]
    intervals = SCALE_INTERVALS[scale.lower()]
    return tuple(root + interval + octave for octave in (0, 12) for interval in intervals)


def make_melody(config: GenerationConfig) -> list[tuple[int, int, int, int]]:
    """Return (start_tick, duration_tick, pitch, velocity) note events."""
    config.validate()
    rng = random.Random(config.seed)
    pitches = scale_notes(config.root_note, config.scale)
    total_ticks = config.bars * BEATS_PER_BAR * TICKS_PER_BEAT
    position = 0
    events: list[tuple[int, int, int, int]] = []

    while position < total_ticks:
        remaining_steps = (total_ticks - position) // STEP_TICKS
        length_steps = min(rng.choice((1, 1, 2, 2, 3, 4)), remaining_steps)
        duration = length_steps * STEP_TICKS
        if rng.random() >= 0.28:
            events.append((position, duration, rng.choice(pitches), rng.randint(55, 112)))
        position += duration
    return events


def generate_midi(config: GenerationConfig, destination: str | Path) -> Path:
    """Generate a single-track MIDI file and return its path."""
    events = make_melody(config)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    midi = MidiFile(ticks_per_beat=TICKS_PER_BEAT)
    track = MidiTrack()
    midi.tracks.append(track)
    track.append(MetaMessage("track_name", name="Generated Melody", time=0))
    track.append(MetaMessage("set_tempo", tempo=bpm2tempo(config.bpm), time=0))
    track.append(Message("program_change", program=0, channel=0, time=0))

    cursor = 0
    for start, duration, pitch, velocity in events:
        track.append(Message("note_on", note=pitch, velocity=velocity, channel=0, time=start - cursor))
        track.append(Message("note_off", note=pitch, velocity=0, channel=0, time=duration))
        cursor = start + duration
    total_ticks = config.bars * BEATS_PER_BAR * TICKS_PER_BEAT
    track.append(MetaMessage("end_of_track", time=total_ticks - cursor))
    midi.save(destination)
    return destination
