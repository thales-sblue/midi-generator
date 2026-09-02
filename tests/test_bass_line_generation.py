"""Deterministic diatonic bass line that follows a reference clip."""

import pytest

from midi_generator.domain import MelodyRequest, NoteEvent, TimeSignature
from midi_generator.generation import generate_bass_line_plan
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


def test_bass_line_follows_the_foundation_one_note_per_sounding_window():
    request = MelodyRequest(120, "C", "major", 1, 42)

    plan = generate_bass_line_plan(request, reference_clip())

    assert [(n.pitch, n.start, n.duration, n.velocity) for n in plan.notes] == [
        (36, 0, 480, 96),
        (40, 480, 480, 96),
        (43, 960, 480, 96),
    ]
    assert plan.total_duration_ticks == 1920
    assert plan.report.note_count == 3
    assert plan.report.pause_count == 1
    assert plan.report.scale == "major"
    assert plan.metadata["generation_mode"] == "bass_line"
    assert plan.metadata["foundation_source"] == "analysis.bass_line_pitches"
    assert plan.metadata["segment_count"] == 4
    assert plan.metadata["sounding_segment_count"] == 3
    assert plan.metadata["silent_segment_count"] == 1


def test_bass_line_is_deterministic_and_ignores_the_seed_for_pitches():
    reference = reference_clip()
    first = generate_bass_line_plan(MelodyRequest(120, "C", "major", 1, 1), reference)
    same = generate_bass_line_plan(MelodyRequest(120, "C", "major", 1, 1), reference)
    other_seed = generate_bass_line_plan(
        MelodyRequest(120, "C", "major", 1, 999), reference
    )

    assert first == same
    assert first.notes == other_seed.notes
    assert first.report.seed == 1
    assert other_seed.report.seed == 999
    assert reference == reference_clip()


def test_bass_line_snaps_foreign_pitches_into_the_scale():
    request = MelodyRequest(120, "C", "minor", 1, 7)

    plan = generate_bass_line_plan(request, reference_clip())

    # E2 (pc 4) is outside C minor and snaps down to Eb2 (39); C2 and G2 stay.
    assert [n.pitch for n in plan.notes] == [36, 39, 43]
    assert plan.metadata["pitch_mapping"] == "nearest_scale_pitch_ties_down"


def test_bass_line_resolves_equidistant_snaps_downward():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(42, 0, 1920, 64),),  # F#2, pc 6, sustained
    )
    request = MelodyRequest(120, "C", "major", 1, 3)

    plan = generate_bass_line_plan(request, reference)

    # pc 5 (below) and pc 7 (above) are both one semitone away; ties go down.
    assert {n.pitch for n in plan.notes} == {41}


def test_sustained_reference_note_feeds_every_window():
    reference = EditableMidiClip(
        length_ticks=1920, notes=(NoteEvent(36, 0, 1920, 55),)
    )
    request = MelodyRequest(120, "C", "major", 1, 5)

    plan = generate_bass_line_plan(request, reference)

    assert [(n.pitch, n.start, n.duration) for n in plan.notes] == [
        (36, 0, 480),
        (36, 480, 480),
        (36, 960, 480),
        (36, 1440, 480),
    ]


def test_segment_beats_widens_the_windows():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(36, 0, 480, 70), NoteEvent(43, 960, 480, 90)),
    )
    request = MelodyRequest(120, "C", "major", 1, 5)

    plan = generate_bass_line_plan(request, reference, segment_beats=2)

    assert [(n.pitch, n.start, n.duration) for n in plan.notes] == [
        (36, 0, 960),
        (43, 960, 960),
    ]
    assert plan.metadata["segment_beats"] == 2
    assert plan.metadata["segment_count"] == 2


def test_final_partial_window_is_clamped_to_the_clip():
    reference = EditableMidiClip(
        length_ticks=1440,
        notes=(NoteEvent(40, 0, 480, 70), NoteEvent(43, 960, 480, 90)),
    )
    request = MelodyRequest(
        120, "C", "major", 1, 5, time_signature=TimeSignature(3, 4)
    )

    plan = generate_bass_line_plan(request, reference, segment_beats=2)

    assert [(n.pitch, n.start, n.duration) for n in plan.notes] == [
        (40, 0, 960),
        (43, 960, 480),
    ]
    assert plan.notes[-1].start + plan.notes[-1].duration == 1440


def test_custom_velocity_is_applied_and_validated():
    plan = generate_bass_line_plan(
        MelodyRequest(120, "C", "major", 1, 5), reference_clip(), velocity=50
    )
    assert all(note.velocity == 50 for note in plan.notes)
    assert plan.metadata["velocity"] == 50

    with pytest.raises(ValueError):
        generate_bass_line_plan(
            MelodyRequest(120, "C", "major", 1, 5), reference_clip(), velocity=0
        )


def test_request_length_must_match_the_reference_clip():
    with pytest.raises(ValueError, match="match the reference clip length"):
        generate_bass_line_plan(
            MelodyRequest(120, "C", "major", 2, 5), reference_clip()
        )


def test_all_muted_reference_is_rejected():
    reference = EditableMidiClip(
        length_ticks=1920, notes=(NoteEvent(36, 0, 480, 70, mute=True),)
    )
    with pytest.raises(ValueError, match="at least one sounding note"):
        generate_bass_line_plan(MelodyRequest(120, "C", "major", 1, 5), reference)


def test_invalid_segment_beats_is_rejected():
    with pytest.raises(ValueError):
        generate_bass_line_plan(
            MelodyRequest(120, "C", "major", 1, 5), reference_clip(), segment_beats=0
        )


def test_default_note_grouping_is_a_per_window_pulse():
    plan = generate_bass_line_plan(
        MelodyRequest(120, "C", "major", 1, 5), reference_clip()
    )
    assert plan.metadata["note_grouping"] == "per_window"


def test_sustain_ties_consecutive_equal_snapped_pitches():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(36, 0, 480, 70),
            NoteEvent(36, 480, 480, 70),
            NoteEvent(43, 960, 480, 90),
        ),
    )
    request = MelodyRequest(120, "C", "major", 1, 5)

    pulse = generate_bass_line_plan(request, reference)
    held = generate_bass_line_plan(request, reference, sustain=True)

    assert [(n.pitch, n.start, n.duration) for n in pulse.notes] == [
        (36, 0, 480),
        (36, 480, 480),
        (43, 960, 480),
    ]
    assert [(n.pitch, n.start, n.duration) for n in held.notes] == [
        (36, 0, 960),
        (43, 960, 480),
    ]
    assert held.report.note_count == 2
    assert held.report.pause_count == 1
    assert held.metadata["note_grouping"] == "sustained"
    assert held == generate_bass_line_plan(request, reference, sustain=True)


def test_sustain_does_not_bridge_a_silent_window():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(36, 0, 480, 70), NoteEvent(36, 960, 480, 70)),
    )
    request = MelodyRequest(120, "C", "major", 1, 5)

    held = generate_bass_line_plan(request, reference, sustain=True)

    assert [(n.pitch, n.start, n.duration) for n in held.notes] == [
        (36, 0, 480),
        (36, 960, 480),
    ]
    assert held.report.note_count == 2
    assert held.report.pause_count == 2


def test_sustain_merges_distinct_foundations_that_snap_to_one_pitch():
    reference = EditableMidiClip(
        length_ticks=960,
        notes=(NoteEvent(40, 0, 480, 70), NoteEvent(39, 480, 480, 70)),
    )
    request = MelodyRequest(
        120, "C", "minor", 1, 5, time_signature=TimeSignature(2, 4)
    )

    held = generate_bass_line_plan(request, reference, sustain=True)

    # E2 (pc 4) snaps down to Eb2 (39); Eb2 is already in C minor. One held note.
    assert [(n.pitch, n.start, n.duration) for n in held.notes] == [(39, 0, 960)]


def test_sustain_must_be_boolean():
    with pytest.raises(ValueError, match="sustain must be a boolean"):
        generate_bass_line_plan(
            MelodyRequest(120, "C", "major", 1, 5), reference_clip(), sustain=1
        )


def test_octave_defaults_to_none_and_keeps_the_source_register():
    plan = generate_bass_line_plan(
        MelodyRequest(120, "C", "major", 1, 5), reference_clip()
    )
    assert plan.metadata["target_octave"] is None
    assert plan.metadata["octave_offset_semitones"] == 0
    assert [n.pitch for n in plan.notes] == [36, 40, 43]


def test_octave_anchors_the_lowest_note_into_the_target_octave():
    # A reference sitting around middle C, asked for octave 2 (MIDI 36..47).
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

    plan = generate_bass_line_plan(request, reference, octave=2)

    # One offset (-24) applies to every note: contour and intervals preserved.
    assert [n.pitch for n in plan.notes] == [36, 40, 43]
    assert plan.metadata["target_octave"] == 2
    assert plan.metadata["octave_offset_semitones"] == -24
    assert 36 <= min(n.pitch for n in plan.notes) <= 47


def test_octave_can_lift_a_low_reference_upward():
    reference = EditableMidiClip(
        length_ticks=960,
        notes=(NoteEvent(24, 0, 480, 70), NoteEvent(28, 480, 480, 70)),
    )
    request = MelodyRequest(
        120, "C", "major", 1, 5, time_signature=TimeSignature(2, 4)
    )

    plan = generate_bass_line_plan(request, reference, octave=3)

    assert plan.metadata["octave_offset_semitones"] == 24
    assert [n.pitch for n in plan.notes] == [48, 52]


def test_octave_rejects_a_shift_that_would_exceed_midi_127():
    reference = EditableMidiClip(
        length_ticks=960,
        notes=(NoteEvent(36, 0, 480, 70), NoteEvent(120, 480, 480, 70)),
    )
    request = MelodyRequest(
        120, "C", "major", 1, 5, time_signature=TimeSignature(2, 4)
    )

    with pytest.raises(ValueError, match="exceeding MIDI 127"):
        generate_bass_line_plan(request, reference, octave=9)


def test_octave_must_be_an_integer_in_range():
    request = MelodyRequest(120, "C", "major", 1, 5)
    with pytest.raises(ValueError, match="octave must be an integer"):
        generate_bass_line_plan(request, reference_clip(), octave=True)
    with pytest.raises(ValueError, match="octave must be an integer"):
        generate_bass_line_plan(request, reference_clip(), octave=42)


def test_octave_combines_with_sustain():
    reference = EditableMidiClip(
        length_ticks=1440,
        notes=(
            NoteEvent(60, 0, 480, 70),
            NoteEvent(60, 480, 480, 70),
            NoteEvent(64, 960, 480, 70),
        ),
    )
    request = MelodyRequest(
        120, "C", "major", 1, 5, time_signature=TimeSignature(3, 4)
    )

    plan = generate_bass_line_plan(request, reference, octave=2, sustain=True)

    assert [(n.pitch, n.start, n.duration) for n in plan.notes] == [
        (36, 0, 960),
        (40, 960, 480),
    ]
    assert plan.metadata["octave_offset_semitones"] == -24


def test_bass_line_plan_serialises_as_payload_v1():
    plan = generate_bass_line_plan(
        MelodyRequest(120, "C", "major", 1, 42), reference_clip()
    )
    payload = composition_to_payload(plan)

    assert payload["schema_version"] == 1
    assert len(payload["notes"]) == 3
    assert payload["total_duration_ticks"] == 1920
