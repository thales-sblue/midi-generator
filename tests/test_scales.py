"""Coverage for the expanded SCALE_INTERVALS: church modes plus harmonic and
melodic minor, across generation, transformations and analysis."""

import pytest

from midi_generator.analysis import rank_scale_candidates
from midi_generator.domain import MelodyRequest, NoteEvent
from midi_generator.domain.music_theory import ROOT_NOTES, SCALE_INTERVALS
from midi_generator.generation import generate_contextual_plan, generate_plan
from midi_generator.transformations import (
    EditableMidiClip,
    constrain_to_scale,
    harmonize_diatonic,
    transpose_diatonic,
)

NEW_MODES = (
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "locrian",
    "harmonic_minor",
    "melodic_minor",
)


def _pitch_classes(root_note: str, scale: str) -> set[int]:
    root = ROOT_NOTES[root_note.upper()]
    return {(root + interval) % 12 for interval in SCALE_INTERVALS[scale]}


def test_every_scale_has_distinct_ascending_intervals_from_the_tonic():
    for name, intervals in SCALE_INTERVALS.items():
        assert list(intervals) == sorted(set(intervals)), name
        assert intervals[0] == 0 and max(intervals) <= 11, name


def test_the_heptatonic_scales_still_have_seven_intervals():
    # Cardinality is no longer a property of the table as a whole: pentatonic
    # and blues scales live in it too, so only these are seven-note scales.
    for name in ("major", "minor", *NEW_MODES):
        assert len(SCALE_INTERVALS[name]) == 7, name


def test_new_modes_are_distinct_from_major_and_minor():
    for mode in NEW_MODES:
        assert SCALE_INTERVALS[mode] != SCALE_INTERVALS["major"]
        assert SCALE_INTERVALS[mode] != SCALE_INTERVALS["minor"]


@pytest.mark.parametrize("scale", ("major", "minor", *NEW_MODES))
def test_generate_plan_stays_in_scale_and_is_deterministic(scale):
    request = MelodyRequest(120, "D", scale, 4, 2026)

    first = generate_plan(request)
    second = generate_plan(request)

    assert first.notes == second.notes
    assert first.report.scale == scale
    allowed = _pitch_classes("D", scale)
    assert {note.pitch % 12 for note in first.notes} <= allowed


def test_contextual_generation_respects_a_mode():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=tuple(
            NoteEvent(pitch, index * 240, 240, 88)
            for index, pitch in enumerate((62, 65, 69, 67, 64, 62, 60, 65))
        ),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "D", "dorian", 2, 7), reference
    )

    allowed = _pitch_classes("D", "dorian")
    assert plan.notes
    assert {note.pitch % 12 for note in plan.notes} <= allowed


def test_constrain_to_scale_snaps_to_a_mode():
    # D dorian is {C, D, E, F, G, A, B}; F# (66) is outside it and the nearest
    # degrees F (65) and G (67) tie, so the downward tie-break picks F.
    clip = EditableMidiClip(
        length_ticks=960, notes=(NoteEvent(66, 0, 240, 90),)
    )

    result = constrain_to_scale(clip, "D", "dorian")

    assert result.notes[0].pitch == 65
    assert constrain_to_scale(result, "D", "dorian") == result


def test_transpose_and_harmonize_diatonic_work_over_a_mode():
    # D and F are both in D dorian.
    clip = EditableMidiClip(
        length_ticks=960,
        notes=(NoteEvent(62, 0, 240, 90), NoteEvent(65, 240, 240, 90)),
    )

    stepped = transpose_diatonic(clip, 2, "D", "dorian")
    harmonised = harmonize_diatonic(clip, 2, "D", "dorian")

    allowed = _pitch_classes("D", "dorian")
    # D up two dorian degrees is F; F up two degrees is A.
    assert [note.pitch for note in stepped.notes] == [65, 69]
    assert {note.pitch % 12 for note in stepped.notes} <= allowed
    assert len(harmonised.notes) == 4
    assert {note.pitch % 12 for note in harmonised.notes} <= allowed


def test_scale_ranking_covers_every_scale_and_ranks_a_mode_diatonic_clip():
    # {C, D, E, F, G, A, B} with D twice: exactly D dorian and its relatives.
    clip = EditableMidiClip(
        length_ticks=1920,
        notes=tuple(
            NoteEvent(pitch, index * 240, 240, 90)
            for index, pitch in enumerate((62, 64, 65, 67, 69, 71, 72, 62))
        ),
    )

    candidates = rank_scale_candidates(clip)

    assert len(candidates) == 12 * len(SCALE_INTERVALS)
    full = {(c.root_note, c.scale) for c in candidates if c.coverage == 1.0}
    assert ("D", "dorian") in full
    assert ("C", "major") in full
    # D occurs twice, so a D-rooted covering scale has the strongest tonic
    # evidence and ranks first.
    assert candidates[0].root_note == "D"
    assert candidates[0].scale == "dorian"
    assert candidates[0].coverage == 1.0
