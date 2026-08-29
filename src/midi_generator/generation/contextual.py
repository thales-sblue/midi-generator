"""Deterministic melody generation shaped by an existing MIDI clip."""

import random

from midi_generator.domain import (
    CompositionPlan,
    GenerationReport,
    MelodyRequest,
    NoteEvent,
)
from midi_generator.domain.music_theory import ROOT_NOTES, SCALE_INTERVALS
from midi_generator.transformations import EditableMidiClip
from midi_generator.validation.musical_validation import validate_plan

from .melody import BEATS_PER_BAR, STEP_TICKS, TICKS_PER_BEAT


def generate_contextual_plan(
    request: MelodyRequest, reference: EditableMidiClip
) -> CompositionPlan:
    """Generate a monophonic plan using a reference clip's objective profile."""
    request.validate()
    if request.root_note.upper() not in ROOT_NOTES:
        raise ValueError("Root note must be one of C, C#, Db, D, etc.")
    if request.scale.lower() not in SCALE_INTERVALS:
        raise ValueError("Scale must be 'major' or 'minor'.")
    reference.validate()

    sounding = tuple(note for note in reference.notes if not note.mute)
    if not sounding:
        raise ValueError("Reference clip must contain at least one sounding note.")

    total_ticks = request.bars * BEATS_PER_BAR * TICKS_PER_BEAT
    step_count = total_ticks // STEP_TICKS
    requested_note_count = _target_note_count(
        len(sounding), reference.length_ticks, reference.ticks_per_beat, request.bars
    )
    target_note_count = min(max(requested_note_count, 1), step_count)
    warnings = ()
    if requested_note_count < 1:
        warnings = ("Contextual density was raised to one note.",)
    elif requested_note_count > step_count:
        warnings = (
            "Contextual density exceeded the monophonic eighth-note grid and was capped.",
        )

    rng = random.Random(request.seed)
    selected_steps = sorted(rng.sample(range(step_count), target_note_count))
    starts = tuple(step * STEP_TICKS for step in selected_steps)
    mean_duration = _round_half_up(
        sum(note.duration for note in sounding), len(sounding)
    )
    lowest_pitch = min(note.pitch for note in sounding)
    highest_pitch = max(note.pitch for note in sounding)
    pitches = _contextual_pitches(
        request.root_note, request.scale, lowest_pitch, highest_pitch
    )
    pitch_groups = _weighted_pitch_groups(pitches, sounding)
    velocities = tuple(note.velocity for note in sounding)

    notes = tuple(
        NoteEvent(
            pitch=_choose_contextual_pitch(rng, pitch_groups),
            start=start,
            duration=min(
                mean_duration,
                (starts[index + 1] if index + 1 < len(starts) else total_ticks)
                - start,
            ),
            velocity=rng.choice(velocities),
        )
        for index, start in enumerate(starts)
    )
    report = GenerationReport(
        note_count=len(notes),
        pause_count=step_count - len(notes),
        duration_ticks=total_ticks,
        scale=request.scale.lower(),
        seed=request.seed,
        warnings=warnings,
    )
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=notes,
        total_duration_ticks=total_ticks,
        report=report,
        metadata={
            "time_signature": "4/4",
            "ticks_per_beat": TICKS_PER_BEAT,
            "generation_mode": "contextual",
            "reference_note_count": len(sounding),
            "reference_lowest_pitch": lowest_pitch,
            "reference_highest_pitch": highest_pitch,
            "target_note_count": target_note_count,
            "pitch_sampling": "reference_pitch_class_distribution",
            "velocity_sampling": "reference_values",
        },
    )
    validate_plan(plan)
    return plan


def _target_note_count(
    reference_note_count: int,
    reference_length_ticks: int,
    reference_ticks_per_beat: int,
    target_bars: int,
) -> int:
    numerator = (
        reference_note_count
        * reference_ticks_per_beat
        * target_bars
        * BEATS_PER_BAR
    )
    return _round_half_up(numerator, reference_length_ticks)


def _contextual_pitches(
    root_note: str, scale: str, lowest_pitch: int, highest_pitch: int
) -> tuple[int, ...]:
    root_pitch_class = ROOT_NOTES[root_note.upper()]
    allowed_pitch_classes = {
        (root_pitch_class + interval) % 12
        for interval in SCALE_INTERVALS[scale.lower()]
    }
    allowed = tuple(
        pitch for pitch in range(128) if pitch % 12 in allowed_pitch_classes
    )
    inside_register = tuple(
        pitch for pitch in allowed if lowest_pitch <= pitch <= highest_pitch
    )
    if inside_register:
        return inside_register

    center_sum = lowest_pitch + highest_pitch
    nearest = min(allowed, key=lambda pitch: (abs(2 * pitch - center_sum), pitch))
    return (nearest,)


def _weighted_pitch_groups(
    pitches: tuple[int, ...], sounding: tuple[NoteEvent, ...]
) -> tuple[tuple[tuple[int, ...], int], ...]:
    histogram = [0] * 12
    for note in sounding:
        histogram[note.pitch % 12] += 1

    groups = tuple(
        (
            tuple(pitch for pitch in pitches if pitch % 12 == pitch_class),
            histogram[pitch_class],
        )
        for pitch_class in range(12)
        if histogram[pitch_class]
        and any(pitch % 12 == pitch_class for pitch in pitches)
    )
    if groups:
        return groups
    return tuple(((pitch,), 1) for pitch in pitches)


def _choose_contextual_pitch(
    rng: random.Random, groups: tuple[tuple[tuple[int, ...], int], ...]
) -> int:
    selection = rng.randrange(sum(weight for _, weight in groups))
    for pitches, weight in groups:
        if selection < weight:
            return rng.choice(pitches)
        selection -= weight
    raise AssertionError("Weighted pitch selection exhausted its groups.")


def _round_half_up(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    return quotient + int(remainder * 2 >= denominator)
