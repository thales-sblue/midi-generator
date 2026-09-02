"""Deterministic diatonic chord bed that follows a reference clip's foundation."""

import pytest

from midi_generator.domain import MelodyRequest, NoteEvent, TimeSignature
from midi_generator.generation import generate_chord_bed_plan
from midi_generator.integration import composition_to_payload
from midi_generator.transformations import EditableMidiClip


def reference_clip():
    """One 4/4 bar: C2, E2, G2 on beats 1-3 and a silent beat 4."""
    return EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(36, 0, 480, 70),
            NoteEvent(40, 480, 480, 80),
            NoteEvent(43, 960, 480, 90),
            NoteEvent(72, 0, 240, 127, mute=True),
        ),
    )


def test_chord_bed_stacks_a_diatonic_triad_on_every_sounding_window():
    request = MelodyRequest(120, "C", "major", 1, 42)

    plan = generate_chord_bed_plan(request, reference_clip())

    assert [(n.pitch, n.start, n.duration, n.velocity) for n in plan.notes] == [
        (36, 0, 480, 80),
        (40, 0, 480, 80),
        (43, 0, 480, 80),
        (40, 480, 480, 80),
        (43, 480, 480, 80),
        (47, 480, 480, 80),
        (43, 960, 480, 80),
        (47, 960, 480, 80),
        (50, 960, 480, 80),
    ]
    assert plan.total_duration_ticks == 1920
    assert plan.report.note_count == 9
    assert plan.report.pause_count == 1
    assert plan.report.scale == "major"
    assert plan.metadata["generation_mode"] == "chord_bed"
    assert plan.metadata["voicing"] == "stacked_scale_thirds"
    assert plan.metadata["chord_size"] == 3
    assert plan.metadata["foundation_source"] == "analysis.bass_line_pitches"
    assert plan.metadata["segment_count"] == 4
    assert plan.metadata["sounding_segment_count"] == 3
    assert plan.metadata["silent_segment_count"] == 1


def test_chord_bed_is_deterministic_and_ignores_the_seed_for_pitches():
    reference = reference_clip()
    first = generate_chord_bed_plan(MelodyRequest(120, "C", "major", 1, 1), reference)
    same = generate_chord_bed_plan(MelodyRequest(120, "C", "major", 1, 1), reference)
    other_seed = generate_chord_bed_plan(
        MelodyRequest(120, "C", "major", 1, 999), reference
    )

    assert first == same
    assert first.notes == other_seed.notes
    assert first.report.seed == 1
    assert other_seed.report.seed == 999
    assert reference == reference_clip()


def test_chord_tones_follow_the_scale_the_foundation_was_snapped_into():
    request = MelodyRequest(120, "C", "minor", 1, 7)

    plan = generate_chord_bed_plan(request, reference_clip())

    # E2 snaps down to Eb2 (39) in C minor and carries an Eb major triad.
    assert [n.pitch for n in plan.notes[3:6]] == [39, 43, 46]
    assert plan.metadata["pitch_mapping"] == "nearest_scale_pitch_ties_down"


def test_chord_size_four_adds_the_diatonic_seventh():
    request = MelodyRequest(120, "C", "major", 1, 5)

    plan = generate_chord_bed_plan(request, reference_clip(), chord_size=4)

    assert [n.pitch for n in plan.notes[:4]] == [36, 40, 43, 47]
    assert plan.report.note_count == 12
    assert plan.metadata["chord_size"] == 4


def test_chord_size_must_be_an_integer_between_two_and_five():
    request = MelodyRequest(120, "C", "major", 1, 5)
    for invalid in (1, 6, True, 3.0):
        with pytest.raises(ValueError, match="chord_size must be an integer"):
            generate_chord_bed_plan(request, reference_clip(), chord_size=invalid)


def test_sustain_ties_every_voice_of_a_repeated_chord():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(36, 0, 480, 70),
            NoteEvent(36, 480, 480, 70),
            NoteEvent(43, 960, 480, 90),
        ),
    )
    request = MelodyRequest(120, "C", "major", 1, 5)

    held = generate_chord_bed_plan(request, reference, sustain=True)

    assert [(n.pitch, n.start, n.duration) for n in held.notes] == [
        (36, 0, 960),
        (40, 0, 960),
        (43, 0, 960),
        (43, 960, 480),
        (47, 960, 480),
        (50, 960, 480),
    ]
    assert held.report.note_count == 6
    assert held.report.pause_count == 1
    assert held.metadata["note_grouping"] == "sustained"


def test_sustain_does_not_bridge_a_silent_window():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(36, 0, 480, 70), NoteEvent(36, 960, 480, 70)),
    )
    request = MelodyRequest(120, "C", "major", 1, 5)

    held = generate_chord_bed_plan(request, reference, sustain=True)

    assert [(n.pitch, n.start, n.duration) for n in held.notes] == [
        (36, 0, 480),
        (40, 0, 480),
        (43, 0, 480),
        (36, 960, 480),
        (40, 960, 480),
        (43, 960, 480),
    ]
    assert held.report.pause_count == 2


def test_default_note_grouping_is_a_per_window_pulse():
    plan = generate_chord_bed_plan(
        MelodyRequest(120, "C", "major", 1, 5), reference_clip()
    )
    assert plan.metadata["note_grouping"] == "per_window"


def test_octave_anchors_the_lowest_voice_and_keeps_the_voicing():
    reference = EditableMidiClip(
        length_ticks=1440,
        notes=(
            NoteEvent(60, 0, 480, 70),
            NoteEvent(64, 480, 480, 70),
            NoteEvent(67, 960, 480, 70),
        ),
    )
    request = MelodyRequest(
        120, "C", "major", 1, 5, time_signature=TimeSignature(3, 4)
    )

    plan = generate_chord_bed_plan(request, reference, octave=3)

    assert [n.pitch for n in plan.notes[:3]] == [48, 52, 55]
    assert min(n.pitch for n in plan.notes) == 48
    assert plan.metadata["target_octave"] == 3
    assert plan.metadata["octave_offset_semitones"] == -12


def test_octave_defaults_to_none_and_keeps_the_source_register():
    plan = generate_chord_bed_plan(
        MelodyRequest(120, "C", "major", 1, 5), reference_clip()
    )
    assert plan.metadata["target_octave"] is None
    assert plan.metadata["octave_offset_semitones"] == 0
    assert plan.notes[0].pitch == 36


def test_chord_bed_rejects_a_voicing_that_would_exceed_midi_127():
    reference = EditableMidiClip(
        length_ticks=1920, notes=(NoteEvent(36, 0, 1920, 70),)
    )
    request = MelodyRequest(120, "C", "major", 1, 42)

    # C9 (120) still carries a triad (120, 124, 127) but no diatonic seventh.
    triad = generate_chord_bed_plan(request, reference, octave=9)
    assert [n.pitch for n in triad.notes[:3]] == [120, 124, 127]

    with pytest.raises(ValueError, match="exceeding MIDI 127"):
        generate_chord_bed_plan(request, reference, octave=9, chord_size=4)


def test_a_high_anchor_the_whole_bed_cannot_carry_is_rejected():
    # The G window would need 130 for its fifth, so the bed cannot sit at C9.
    with pytest.raises(ValueError, match="exceeding MIDI 127"):
        generate_chord_bed_plan(
            MelodyRequest(120, "C", "major", 1, 42), reference_clip(), octave=9
        )


def test_segment_beats_widens_the_windows():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(36, 0, 480, 70), NoteEvent(43, 960, 480, 90)),
    )
    request = MelodyRequest(120, "C", "major", 1, 5)

    plan = generate_chord_bed_plan(request, reference, segment_beats=2)

    assert [(n.pitch, n.start, n.duration) for n in plan.notes] == [
        (36, 0, 960),
        (40, 0, 960),
        (43, 0, 960),
        (43, 960, 960),
        (47, 960, 960),
        (50, 960, 960),
    ]
    assert plan.metadata["segment_beats"] == 2


def test_custom_velocity_is_applied_and_validated():
    plan = generate_chord_bed_plan(
        MelodyRequest(120, "C", "major", 1, 5), reference_clip(), velocity=64
    )
    assert all(note.velocity == 64 for note in plan.notes)
    assert plan.metadata["velocity"] == 64

    with pytest.raises(ValueError, match="velocity must be an integer"):
        generate_chord_bed_plan(
            MelodyRequest(120, "C", "major", 1, 5), reference_clip(), velocity=0
        )


def test_request_length_must_match_the_reference_clip():
    with pytest.raises(ValueError, match="match the reference clip length"):
        generate_chord_bed_plan(MelodyRequest(120, "C", "major", 2, 5), reference_clip())


def test_all_muted_reference_is_rejected():
    reference = EditableMidiClip(
        length_ticks=1920, notes=(NoteEvent(36, 0, 480, 70, mute=True),)
    )
    with pytest.raises(ValueError, match="at least one sounding note"):
        generate_chord_bed_plan(MelodyRequest(120, "C", "major", 1, 5), reference)


def test_chord_bed_plan_serialises_as_payload_v1():
    plan = generate_chord_bed_plan(
        MelodyRequest(120, "C", "major", 1, 42), reference_clip()
    )
    payload = composition_to_payload(plan)

    assert payload["schema_version"] == 1
    assert len(payload["notes"]) == 9
    assert payload["total_duration_ticks"] == 1920
