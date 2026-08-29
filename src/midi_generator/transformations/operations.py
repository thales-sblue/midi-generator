"""Small, predictable MIDI transformations with no external dependencies."""

import random
from dataclasses import replace

from midi_generator.domain.music_theory import ROOT_NOTES, SCALE_INTERVALS

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


def staccato(clip: EditableMidiClip, max_duration: int) -> EditableMidiClip:
    """Shorten notes to a maximum tick duration without changing their onsets."""
    clip.validate()
    if not _is_int(max_duration) or max_duration <= 0:
        raise ValueError("max_duration must be a positive integer of ticks.")
    return replace(
        clip,
        notes=tuple(
            replace(note, duration=min(note.duration, max_duration))
            for note in clip.notes
        ),
    )


def velocity_ramp(
    clip: EditableMidiClip, start_velocity: int, end_velocity: int
) -> EditableMidiClip:
    """Shape note velocities linearly between the first and last onset."""
    clip.validate()
    for name, value in (
        ("start_velocity", start_velocity),
        ("end_velocity", end_velocity),
    ):
        if not _is_int(value) or not 1 <= value <= 127:
            raise ValueError(f"{name} must be an integer between 1 and 127.")
    if not clip.notes:
        return replace(clip)

    first_start = min(note.start for note in clip.notes)
    last_start = max(note.start for note in clip.notes)
    if first_start == last_start:
        return replace(
            clip,
            notes=tuple(
                replace(note, velocity=start_velocity) for note in clip.notes
            ),
        )

    delta = end_velocity - start_velocity
    span = last_start - first_start
    return replace(
        clip,
        notes=tuple(
            replace(
                note,
                velocity=start_velocity
                + _round_ratio(delta * (note.start - first_start), span),
            )
            for note in clip.notes
        ),
    )


def constrain_to_scale(
    clip: EditableMidiClip, root_note: str, scale: str
) -> EditableMidiClip:
    """Move out-of-scale pitches to the nearest pitch in a major or minor scale.

    Equidistant choices resolve downward, which makes the operation fully
    deterministic and avoids an unintended upward melodic drift.
    """
    clip.validate()
    root, intervals = _scale_definition(root_note, scale)
    allowed_pitch_classes = {(root + interval) % 12 for interval in intervals}
    return replace(
        clip,
        notes=tuple(
            replace(note, pitch=_nearest_scale_pitch(note.pitch, allowed_pitch_classes))
            for note in clip.notes
        ),
    )


def transpose_diatonic(
    clip: EditableMidiClip, steps: int, root_note: str, scale: str
) -> EditableMidiClip:
    """Transpose pitches by scale degrees, snapping foreign pitches downward on ties."""
    clip.validate()
    if not _is_int(steps):
        raise ValueError("steps must be an integer.")
    root, intervals = _scale_definition(root_note, scale)
    allowed_pitch_classes = {(root + interval) % 12 for interval in intervals}
    scale_pitches = tuple(
        pitch for pitch in range(128) if pitch % 12 in allowed_pitch_classes
    )
    positions = {pitch: index for index, pitch in enumerate(scale_pitches)}
    source_pitches = [
        _nearest_scale_pitch(note.pitch, allowed_pitch_classes) for note in clip.notes
    ]
    target_indices = [positions[pitch] + steps for pitch in source_pitches]
    if any(index < 0 or index >= len(scale_pitches) for index in target_indices):
        raise ValueError("Diatonic transposition would produce a pitch outside 0..127.")
    return replace(
        clip,
        notes=tuple(
            replace(note, pitch=scale_pitches[index])
            for note, index in zip(clip.notes, target_indices, strict=True)
        ),
    )


def harmonize_diatonic(
    clip: EditableMidiClip, steps: int, root_note: str, scale: str
) -> EditableMidiClip:
    """Add a parallel diatonic voice while preserving every original note."""
    clip.validate()
    if not _is_int(steps) or steps == 0:
        raise ValueError("steps must be a non-zero integer.")
    root, intervals = _scale_definition(root_note, scale)
    allowed = {(root + interval) % 12 for interval in intervals}
    if any(note.pitch % 12 not in allowed for note in clip.notes):
        raise ValueError("All source pitches must belong to the requested scale.")
    pitches = tuple(pitch for pitch in range(128) if pitch % 12 in allowed)
    positions = {pitch: index for index, pitch in enumerate(pitches)}
    indices = [positions[note.pitch] + steps for note in clip.notes]
    if any(index < 0 or index >= len(pitches) for index in indices):
        raise ValueError("Diatonic harmony would produce a pitch outside 0..127.")
    existing = set(clip.notes)
    harmony = tuple(
        replace(note, pitch=pitches[index])
        for note, index in zip(clip.notes, indices, strict=True)
        if replace(note, pitch=pitches[index]) not in existing
    )
    return replace(clip, notes=clip.notes + harmony)


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


def _round_ratio(numerator: int, denominator: int) -> int:
    magnitude, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 >= denominator:
        magnitude += 1
    return magnitude if numerator >= 0 else -magnitude


def _scale_definition(root_note: str, scale: str) -> tuple[int, tuple[int, ...]]:
    if not isinstance(root_note, str) or root_note.upper() not in ROOT_NOTES:
        raise ValueError("root_note must be one of C, C#, Db, D, etc.")
    if not isinstance(scale, str) or scale.lower() not in SCALE_INTERVALS:
        raise ValueError("scale must be 'major' or 'minor'.")
    return ROOT_NOTES[root_note.upper()], SCALE_INTERVALS[scale.lower()]


def _nearest_scale_pitch(pitch: int, allowed_pitch_classes: set[int]) -> int:
    for distance in range(13):
        lower = pitch - distance
        if lower >= 0 and lower % 12 in allowed_pitch_classes:
            return lower
        upper = pitch + distance
        if upper <= 127 and upper % 12 in allowed_pitch_classes:
            return upper
    raise AssertionError("Every scale must contain a reachable MIDI pitch.")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
