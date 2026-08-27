"""Small, predictable MIDI transformations with no external dependencies."""

import random
from dataclasses import replace

from .clip import EditableMidiClip

GRID_TICKS = {"1/4": 480, "1/8": 240, "1/16": 120}


def transpose(clip: EditableMidiClip, semitones: int) -> EditableMidiClip:
    """Move every pitch by an integer number of semitones."""
    clip.validate()
    if not _is_int(semitones):
        raise ValueError("semitones must be an integer.")
    pitches = [note.pitch + semitones for note in clip.notes]
    if any(pitch < 0 or pitch > 127 for pitch in pitches):
        raise ValueError("Transposition would produce a pitch outside 0..127.")
    return replace(
        clip,
        notes=tuple(
            replace(note, pitch=pitch)
            for note, pitch in zip(clip.notes, pitches, strict=True)
        ),
    )


def invert(clip: EditableMidiClip, axis_pitch: int) -> EditableMidiClip:
    """Reflect every pitch around an integer MIDI note axis."""
    clip.validate()
    if not _is_int(axis_pitch) or not 0 <= axis_pitch <= 127:
        raise ValueError("axis_pitch must be an integer between 0 and 127.")
    pitches = [2 * axis_pitch - note.pitch for note in clip.notes]
    if any(pitch < 0 or pitch > 127 for pitch in pitches):
        raise ValueError("Inversion would produce a pitch outside 0..127.")
    return replace(
        clip,
        notes=tuple(
            replace(note, pitch=pitch)
            for note, pitch in zip(clip.notes, pitches, strict=True)
        ),
    )


def retrograde(clip: EditableMidiClip) -> EditableMidiClip:
    """Reflect every note in time around the clip boundaries."""
    clip.validate()
    return replace(
        clip,
        notes=tuple(
            replace(note, start=clip.length_ticks - note.start - note.duration)
            for note in clip.notes
        ),
    )


def legato(clip: EditableMidiClip) -> EditableMidiClip:
    """Set each note end to the next distinct onset or the clip boundary."""
    clip.validate()
    starts = sorted({note.start for note in clip.notes})
    next_start = {
        start: starts[index + 1] if index + 1 < len(starts) else clip.length_ticks
        for index, start in enumerate(starts)
    }
    return replace(
        clip,
        notes=tuple(
            replace(note, duration=next_start[note.start] - note.start)
            for note in clip.notes
        ),
    )


def quantize(clip: EditableMidiClip, grid: str) -> EditableMidiClip:
    """Quantize starts to the nearest grid; keep duration unless the clip truncates it."""
    clip.validate()
    if grid not in GRID_TICKS:
        choices = ", ".join(GRID_TICKS)
        raise ValueError(f"grid must be one of: {choices}.")
    grid_ticks = GRID_TICKS[grid]
    last_grid_start = ((clip.length_ticks - 1) // grid_ticks) * grid_ticks
    notes = []
    for note in clip.notes:
        start = min(_round_to_grid(note.start, grid_ticks), last_grid_start)
        duration = min(note.duration, clip.length_ticks - start)
        notes.append(replace(note, start=start, duration=duration))
    return replace(clip, notes=tuple(notes))


def humanize(
    clip: EditableMidiClip,
    seed: int,
    max_timing_shift: int,
    max_velocity_delta: int,
) -> EditableMidiClip:
    """Apply bounded tick and velocity offsets from a local seeded RNG."""
    clip.validate()
    if not _is_int(seed):
        raise ValueError("seed must be an integer.")
    if not _is_int(max_timing_shift) or max_timing_shift < 0:
        raise ValueError("max_timing_shift must be a non-negative integer of ticks.")
    if not _is_int(max_velocity_delta) or max_velocity_delta < 0:
        raise ValueError("max_velocity_delta must be a non-negative integer.")
    if max_velocity_delta > 126:
        raise ValueError("max_velocity_delta must not exceed 126.")

    rng = random.Random(seed)
    notes = []
    for note in clip.notes:
        shift = rng.randint(-max_timing_shift, max_timing_shift)
        velocity_delta = rng.randint(-max_velocity_delta, max_velocity_delta)
        latest_start = clip.length_ticks - note.duration
        start = min(max(note.start + shift, 0), latest_start)
        velocity = min(max(note.velocity + velocity_delta, 1), 127)
        notes.append(replace(note, start=start, velocity=velocity))
    return replace(clip, notes=tuple(notes))


def _round_to_grid(position: int, grid_ticks: int) -> int:
    quotient, remainder = divmod(position, grid_ticks)
    if remainder * 2 >= grid_ticks:
        quotient += 1
    return quotient * grid_ticks


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
