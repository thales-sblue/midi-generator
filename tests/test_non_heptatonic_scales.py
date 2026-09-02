"""Pentatonic and blues scales alongside the seven-note table."""

from midi_generator.analysis import rank_scale_candidates
from midi_generator.domain import (
    MelodyRequest,
    NoteEvent,
    TimeSignature,
    scale_pitch_classes,
    scale_pitches,
)
from midi_generator.domain.music_theory import SCALE_INTERVALS
from midi_generator.generation import (
    generate_bass_line_plan,
    generate_chord_bed_plan,
    generate_contextual_plan,
    generate_plan,
)
from midi_generator.transformations import (
    EditableMidiClip,
    constrain_to_scale,
    harmonize_diatonic,
    transpose_diatonic,
)

NON_HEPTATONIC = ("major_pentatonic", "minor_pentatonic", "blues")


def melodic_clip(pitches, *, ticks=480):
    return EditableMidiClip(
        length_ticks=ticks * len(pitches),
        notes=tuple(
            NoteEvent(pitch, index * ticks, ticks, 80)
            for index, pitch in enumerate(pitches)
        ),
    )


def test_the_table_gains_the_non_heptatonic_scales():
    assert SCALE_INTERVALS["major_pentatonic"] == (0, 2, 4, 7, 9)
    assert SCALE_INTERVALS["minor_pentatonic"] == (0, 3, 5, 7, 10)
    assert SCALE_INTERVALS["blues"] == (0, 3, 5, 6, 7, 10)


def test_heptatonic_scales_keep_their_place_at_the_head_of_the_table():
    names = tuple(SCALE_INTERVALS)
    assert names[0] == "major" and names[1] == "minor"
    # Tie-breaks in the ranking follow insertion order, so every seven-note
    # scale has to stay ahead of the newcomers.
    assert names[-len(NON_HEPTATONIC) :] == NON_HEPTATONIC
    assert all(len(SCALE_INTERVALS[name]) == 7 for name in names[: -len(NON_HEPTATONIC)])


def test_scale_helpers_report_the_real_cardinality():
    assert scale_pitch_classes("C", "major_pentatonic") == frozenset({0, 2, 4, 7, 9})
    assert scale_pitch_classes("C", "blues") == frozenset({0, 3, 5, 6, 7, 10})

    octave = [pitch for pitch in scale_pitches("C", "major_pentatonic") if 60 <= pitch < 72]
    assert octave == [60, 62, 64, 67, 69]


def test_the_heuristic_generator_stays_inside_a_pentatonic_scale():
    plan = generate_plan(MelodyRequest(120, "A", "minor_pentatonic", 4, 2026))

    allowed = scale_pitch_classes("A", "minor_pentatonic")
    assert plan.notes
    assert all(note.pitch % 12 in allowed for note in plan.notes)
    assert plan.report.scale == "minor_pentatonic"


def test_contextual_generation_stays_inside_the_blues_scale():
    reference = melodic_clip([60, 61, 62, 63, 64, 65, 66, 67])
    request = MelodyRequest(120, "C", "blues", 2, 11)

    plan = generate_contextual_plan(request, reference)

    allowed = scale_pitch_classes("C", "blues")
    assert plan.notes
    assert all(note.pitch % 12 in allowed for note in plan.notes)


def test_constrain_to_scale_snaps_into_a_pentatonic():
    clip = melodic_clip([60, 61, 65, 66])

    snapped = constrain_to_scale(clip, "C", "major_pentatonic")

    # 61 ties down to 60; 65 and 66 have no fourth in the scale and reach 64/67.
    assert [note.pitch for note in snapped.notes] == [60, 60, 64, 67]


def test_diatonic_transposition_moves_by_pentatonic_degrees():
    clip = melodic_clip([60, 64])

    moved = transpose_diatonic(clip, 1, "C", "major_pentatonic")

    # One degree of C major pentatonic: C -> D (a tone), E -> G (a minor third).
    assert [note.pitch for note in moved.notes] == [62, 67]


def test_diatonic_harmony_stacks_pentatonic_degrees():
    clip = melodic_clip([60])

    harmonised = harmonize_diatonic(clip, 2, "C", "major_pentatonic")

    # Two degrees above C in C major pentatonic is E, not the heptatonic third.
    assert sorted(note.pitch for note in harmonised.notes) == [60, 64]


def test_a_blues_riff_outranks_every_seven_note_scale():
    # Both Gb and G sound, which no scale in the heptatonic table contains.
    riff = melodic_clip([60, 63, 65, 66, 67, 70])

    best = rank_scale_candidates(riff)[0]

    assert (best.root_note, best.scale) == ("C", "blues")
    assert best.coverage == 1.0


def test_a_seven_note_scale_still_wins_a_tie_against_a_pentatonic():
    triad = melodic_clip([60, 64, 67])

    ranking = rank_scale_candidates(triad)
    names = [(candidate.root_note, candidate.scale) for candidate in ranking]

    assert names[0] == ("C", "major")
    assert names.index(("C", "major")) < names.index(("C", "major_pentatonic"))


def test_the_ranking_covers_every_scale_of_the_table():
    ranking = rank_scale_candidates(melodic_clip([60, 62, 64]))

    assert len(ranking) == 12 * len(SCALE_INTERVALS)


def test_the_bass_generator_snaps_onto_a_pentatonic_foundation():
    reference = melodic_clip([60, 61, 65])
    request = MelodyRequest(
        120, "C", "major_pentatonic", 1, 5, time_signature=TimeSignature(3, 4)
    )

    plan = generate_bass_line_plan(request, reference)

    # 61 ties down to 60; 65 has no fourth in the scale and reaches 64.
    assert [note.pitch for note in plan.notes] == [60, 60, 64]


def test_the_chord_bed_stacks_scale_degrees_rather_than_thirds():
    reference = melodic_clip([60])
    request = MelodyRequest(
        120, "C", "major_pentatonic", 1, 5, time_signature=TimeSignature(1, 4)
    )

    plan = generate_chord_bed_plan(request, reference)

    # Every other degree of C major pentatonic: C, E, A — a third then a fourth.
    assert [note.pitch for note in plan.notes] == [60, 64, 69]
    assert plan.metadata["voicing"] == "stacked_scale_degrees"
