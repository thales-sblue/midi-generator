"""Deterministic melody generation shaped by an existing MIDI clip."""

import random

from midi_generator.analysis import top_line_intervals
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

DURATION_SEED_SALT = 0x4455524154494F4E


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
    reference_onsets = tuple(sorted({note.start for note in sounding}))

    total_ticks = request.bars * BEATS_PER_BAR * TICKS_PER_BEAT
    step_count = total_ticks // STEP_TICKS
    requested_note_count = _target_note_count(
        len(reference_onsets),
        reference.length_ticks,
        reference.ticks_per_beat,
        request.bars,
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
    duration_rng = random.Random(request.seed ^ DURATION_SEED_SALT)
    phase_weights = _onset_phase_weights(
        reference_onsets, reference.ticks_per_beat
    )
    selected_steps = _sample_contextual_steps(
        rng, step_count, target_note_count, phase_weights
    )
    starts = tuple(step * STEP_TICKS for step in selected_steps)
    durations = tuple(note.duration for note in sounding)
    lowest_pitch = min(note.pitch for note in sounding)
    highest_pitch = max(note.pitch for note in sounding)
    pitches = _contextual_pitches(
        request.root_note, request.scale, lowest_pitch, highest_pitch
    )
    pitch_groups = _weighted_pitch_groups(pitches, sounding)
    motion_weights = _melodic_motion_weights(top_line_intervals(sounding))
    velocities = tuple(note.velocity for note in sounding)

    notes = []
    for index, start in enumerate(starts):
        previous_pitch = notes[-1].pitch if notes else None
        motion = (
            _choose_melodic_motion(rng, motion_weights)
            if previous_pitch is not None and motion_weights
            else None
        )
        notes.append(
            NoteEvent(
                pitch=_choose_contextual_pitch(
                    rng, pitch_groups, previous_pitch, motion
                ),
                start=start,
                duration=min(
                    duration_rng.choice(durations),
                    (
                        starts[index + 1]
                        if index + 1 < len(starts)
                        else total_ticks
                    )
                    - start,
                ),
                velocity=rng.choice(velocities),
            )
        )
    note_events = tuple(notes)
    report = GenerationReport(
        note_count=len(note_events),
        pause_count=step_count - len(note_events),
        duration_ticks=total_ticks,
        scale=request.scale.lower(),
        seed=request.seed,
        warnings=warnings,
    )
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=note_events,
        total_duration_ticks=total_ticks,
        report=report,
        metadata={
            "time_signature": "4/4",
            "ticks_per_beat": TICKS_PER_BEAT,
            "generation_mode": "contextual",
            "reference_note_count": len(sounding),
            "reference_onset_count": len(reference_onsets),
            "reference_lowest_pitch": lowest_pitch,
            "reference_highest_pitch": highest_pitch,
            "target_note_count": target_note_count,
            "rhythm_sampling": "reference_onset_phase_distribution",
            "pitch_sampling": "reference_pitch_class_distribution",
            "motion_sampling": "reference_top_line_distribution",
            "duration_sampling": "reference_values",
            "velocity_sampling": "reference_values",
        },
    )
    validate_plan(plan)
    return plan


def _target_note_count(
    reference_onset_count: int,
    reference_length_ticks: int,
    reference_ticks_per_beat: int,
    target_bars: int,
) -> int:
    numerator = (
        reference_onset_count
        * reference_ticks_per_beat
        * target_bars
        * BEATS_PER_BAR
    )
    return _round_half_up(numerator, reference_length_ticks)


def _onset_phase_weights(
    onsets: tuple[int, ...], ticks_per_beat: int
) -> tuple[int, ...]:
    steps_per_bar = BEATS_PER_BAR * TICKS_PER_BEAT // STEP_TICKS
    bar_ticks = BEATS_PER_BAR * ticks_per_beat
    weights = [0] * steps_per_bar
    for onset in onsets:
        phase = _round_half_up(
            (onset % bar_ticks) * steps_per_bar, bar_ticks
        ) % steps_per_bar
        weights[phase] += 1
    return tuple(weights)


def _sample_contextual_steps(
    rng: random.Random,
    step_count: int,
    target_note_count: int,
    phase_weights: tuple[int, ...],
) -> list[int]:
    remaining = list(range(step_count))
    selected = []
    for _ in range(target_note_count):
        weights = tuple(
            phase_weights[step % len(phase_weights)] for step in remaining
        )
        total_weight = sum(weights)
        if total_weight:
            selection = rng.randrange(total_weight)
            selected_index = 0
            for index, weight in enumerate(weights):
                if selection < weight:
                    selected_index = index
                    break
                selection -= weight
        else:
            selected_index = rng.randrange(len(remaining))
        selected.append(remaining.pop(selected_index))
    return sorted(selected)


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
    rng: random.Random,
    groups: tuple[tuple[tuple[int, ...], int], ...],
    previous_pitch: int | None = None,
    motion: int | None = None,
) -> int:
    eligible_groups = _eligible_pitch_groups(groups, previous_pitch, motion)
    selection = rng.randrange(sum(weight for _, weight in eligible_groups))
    for pitches, weight in eligible_groups:
        if selection < weight:
            return rng.choice(pitches)
        selection -= weight
    raise AssertionError("Weighted pitch selection exhausted its groups.")


def _eligible_pitch_groups(
    groups: tuple[tuple[tuple[int, ...], int], ...],
    previous_pitch: int | None,
    motion: int | None,
) -> tuple[tuple[tuple[int, ...], int], ...]:
    if previous_pitch is None or motion is None:
        return groups
    eligible = tuple(
        (
            tuple(
                pitch
                for pitch in pitches
                if (pitch > previous_pitch and motion > 0)
                or (pitch < previous_pitch and motion < 0)
                or (pitch == previous_pitch and motion == 0)
            ),
            weight,
        )
        for pitches, weight in groups
    )
    eligible = tuple(group for group in eligible if group[0])
    if eligible:
        return eligible
    return tuple(
        ((previous_pitch,), weight)
        for pitches, weight in groups
        if previous_pitch in pitches
    )


def _melodic_motion_weights(
    intervals: tuple[int, ...]
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (motion, count)
        for motion, count in (
            (-1, sum(interval < 0 for interval in intervals)),
            (0, sum(interval == 0 for interval in intervals)),
            (1, sum(interval > 0 for interval in intervals)),
        )
        if count
    )


def _choose_melodic_motion(
    rng: random.Random, weights: tuple[tuple[int, int], ...]
) -> int:
    selection = rng.randrange(sum(weight for _, weight in weights))
    for motion, weight in weights:
        if selection < weight:
            return motion
        selection -= weight
    raise AssertionError("Weighted melodic motion selection exhausted its groups.")


def _round_half_up(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    return quotient + int(remainder * 2 >= denominator)
