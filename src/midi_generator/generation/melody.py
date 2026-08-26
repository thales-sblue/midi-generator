"""Deterministic melody composition, independent of file formats."""

import random

from midi_generator.domain import CompositionPlan, GenerationReport, MelodyRequest, NoteEvent
from midi_generator.validation.musical_validation import validate_plan

TICKS_PER_BEAT = 480
BEATS_PER_BAR = 4
STEP_TICKS = TICKS_PER_BEAT // 2

ROOT_NOTES = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
    "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
    "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}
SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
}


def scale_notes(root_note: str, scale: str) -> tuple[int, ...]:
    root = 60 + ROOT_NOTES[root_note.upper()]
    intervals = SCALE_INTERVALS[scale.lower()]
    return tuple(root + interval + octave for octave in (0, 12) for interval in intervals)


def generate_plan(request: MelodyRequest) -> CompositionPlan:
    """Compose a deterministic, library-independent melody plan."""
    request.validate()
    if request.root_note.upper() not in ROOT_NOTES:
        raise ValueError("Root note must be one of C, C#, Db, D, etc.")
    if request.scale.lower() not in SCALE_INTERVALS:
        raise ValueError("Scale must be 'major' or 'minor'.")

    rng = random.Random(request.seed)
    pitches = scale_notes(request.root_note, request.scale)
    total_ticks = request.bars * BEATS_PER_BAR * TICKS_PER_BEAT
    position = 0
    pauses = 0
    notes: list[NoteEvent] = []

    while position < total_ticks:
        remaining_steps = (total_ticks - position) // STEP_TICKS
        length_steps = min(rng.choice((1, 1, 2, 2, 3, 4)), remaining_steps)
        duration = length_steps * STEP_TICKS
        if rng.random() >= 0.28:
            notes.append(NoteEvent(rng.choice(pitches), position, duration, rng.randint(55, 112)))
        else:
            pauses += 1
        position += duration

    report = GenerationReport(len(notes), pauses, total_ticks, request.scale.lower(), request.seed)
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=tuple(notes),
        total_duration_ticks=total_ticks,
        report=report,
        metadata={"time_signature": "4/4", "ticks_per_beat": TICKS_PER_BEAT},
    )
    validate_plan(plan)
    return plan
