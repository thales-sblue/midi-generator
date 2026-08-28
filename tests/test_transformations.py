from midi_generator.domain import NoteEvent
from midi_generator.transformations import (
    EditableMidiClip,
    constrain_to_scale,
    humanize,
    harmonize_diatonic,
    invert,
    legato,
    quantize,
    retrograde,
    staccato,
    transpose,
    transpose_diatonic,
)


def make_clip(*notes, length_ticks=1920):
    return EditableMidiClip(length_ticks=length_ticks, notes=tuple(notes))


def test_transpose_up_and_down_preserves_other_properties_and_input():
    note = NoteEvent(60, 120, 240, 91, channel=2, track=3, mute=True)
    clip = make_clip(note)

    up = transpose(clip, 12)
    down = transpose(make_clip(NoteEvent(64, 120, 240, 91)), -12)

    assert up.notes == (NoteEvent(72, 120, 240, 91, 2, 3, True),)
    assert down.notes[0].pitch == 52
    assert clip.notes == (note,)
    assert up is not clip


def test_transpose_rejects_entire_operation_if_any_pitch_is_invalid():
    clip = make_clip(NoteEvent(60, 0, 120, 90), NoteEvent(120, 120, 120, 80))

    try:
        transpose(clip, 12)
    except ValueError as error:
        assert "outside 0..127" in str(error)
    else:
        raise AssertionError("invalid transposition was accepted")

    assert [note.pitch for note in clip.notes] == [60, 120]


def test_invert_reflects_pitches_around_axis_and_preserves_other_properties():
    original = (
        NoteEvent(60, 120, 240, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 480, 120, 82),
        NoteEvent(67, 720, 360, 73),
    )
    clip = make_clip(*original)

    result = invert(clip, axis_pitch=64)

    assert result.notes == (
        NoteEvent(68, 120, 240, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 480, 120, 82),
        NoteEvent(61, 720, 360, 73),
    )
    assert clip.notes == original
    assert invert(result, axis_pitch=64) == clip


def test_invert_rejects_invalid_axis_and_out_of_range_result_atomically():
    clip = make_clip(NoteEvent(10, 0, 120, 90), NoteEvent(60, 120, 120, 80))

    for axis_pitch, message in [(True, "axis_pitch"), (0, "outside 0..127")]:
        try:
            invert(clip, axis_pitch)
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("invalid inversion was accepted")

    assert [note.pitch for note in clip.notes] == [10, 60]


def test_retrograde_reflects_note_boundaries_and_preserves_note_properties():
    original = (
        NoteEvent(60, 0, 120, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 360, 240, 82),
        NoteEvent(67, 1680, 240, 73),
    )
    clip = make_clip(*original)

    result = retrograde(clip)

    assert result.notes == (
        NoteEvent(60, 1800, 120, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 1320, 240, 82),
        NoteEvent(67, 0, 240, 73),
    )
    assert clip.notes == original
    assert result is not clip


def test_retrograde_is_an_exact_involution_for_valid_clips():
    clip = make_clip(
        NoteEvent(60, 120, 180, 90),
        NoteEvent(64, 120, 360, 80),
        length_ticks=1000,
    )

    assert retrograde(retrograde(clip)) == clip


def test_legato_groups_chords_and_closes_gaps_and_overlaps_by_onset():
    original = (
        NoteEvent(67, 720, 120, 73),
        NoteEvent(60, 0, 120, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 0, 600, 82),
        NoteEvent(65, 480, 600, 77),
    )
    clip = make_clip(*original)

    result = legato(clip)

    assert result.notes == (
        NoteEvent(67, 720, 1200, 73),
        NoteEvent(60, 0, 480, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 0, 480, 82),
        NoteEvent(65, 480, 240, 77),
    )
    assert clip.notes == original
    assert legato(result) == result


def test_legato_accepts_an_empty_clip_without_changing_its_length():
    clip = make_clip(length_ticks=960)

    result = legato(clip)

    assert result == clip
    assert result is not clip


def test_staccato_caps_duration_and_preserves_onsets_and_note_properties():
    original = (
        NoteEvent(60, 0, 600, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 720, 90, 82),
    )
    clip = make_clip(*original)

    result = staccato(clip, max_duration=120)

    assert result.notes == (
        NoteEvent(60, 0, 120, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 720, 90, 82),
    )
    assert clip.notes == original
    assert staccato(result, max_duration=120) == result


def test_staccato_rejects_non_positive_or_non_integer_duration():
    clip = make_clip(NoteEvent(60, 0, 240, 90))

    for max_duration in (0, -1, True, 1.5):
        try:
            staccato(clip, max_duration)
        except ValueError as error:
            assert "positive integer" in str(error)
        else:
            raise AssertionError("invalid staccato duration was accepted")


def test_constrain_to_scale_snaps_only_out_of_scale_notes_and_preserves_properties():
    original = (
        NoteEvent(61, 0, 120, 91, channel=2, track=3, mute=True),
        NoteEvent(62, 240, 240, 82),
        NoteEvent(66, 480, 120, 73),
    )
    clip = make_clip(*original)

    result = constrain_to_scale(clip, "C", "major")

    assert result.notes == (
        NoteEvent(60, 0, 120, 91, channel=2, track=3, mute=True),
        original[1],
        NoteEvent(65, 480, 120, 73),
    )
    assert clip.notes == original
    assert constrain_to_scale(result, "C", "major") == result


def test_constrain_to_scale_uses_downward_tie_break_and_respects_midi_edges():
    clip = make_clip(NoteEvent(1, 0, 120, 90), NoteEvent(127, 120, 120, 80))

    result = constrain_to_scale(clip, "C", "major")

    assert [note.pitch for note in result.notes] == [0, 127]


def test_constrain_to_scale_rejects_unknown_tonality_without_mutating_input():
    clip = make_clip(NoteEvent(61, 0, 120, 90))

    for root_note, scale, message in [("H", "major", "root_note"), ("C", "dorian", "scale")]:
        try:
            constrain_to_scale(clip, root_note, scale)
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("invalid tonality was accepted")

    assert clip.notes[0].pitch == 61


def test_transpose_diatonic_moves_by_scale_degrees_and_preserves_properties():
    original = (
        NoteEvent(60, 0, 120, 91, channel=2, track=3, mute=True),
        NoteEvent(64, 240, 120, 82),
        NoteEvent(61, 480, 120, 73),
    )
    clip = make_clip(*original)

    result = transpose_diatonic(clip, 2, "C", "major")

    assert result.notes == (
        NoteEvent(64, 0, 120, 91, channel=2, track=3, mute=True),
        NoteEvent(67, 240, 120, 82),
        NoteEvent(64, 480, 120, 73),
    )
    assert clip.notes == original


def test_transpose_diatonic_rejects_invalid_steps_and_out_of_range_atomically():
    clip = make_clip(NoteEvent(127, 0, 120, 90))

    for steps, message in [(True, "steps"), (1, "outside 0..127")]:
        try:
            transpose_diatonic(clip, steps, "C", "major")
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("invalid diatonic transposition was accepted")

    assert clip.notes[0].pitch == 127


def test_harmonize_diatonic_adds_a_voice_without_altering_source_notes():
    original = (NoteEvent(60, 0, 120, 90, channel=2, track=3, mute=True),)
    clip = make_clip(*original)

    result = harmonize_diatonic(clip, 2, "C", "major")

    assert result.notes == original + (NoteEvent(64, 0, 120, 90, 2, 3, True),)
    assert clip.notes == original


def test_harmonize_diatonic_rejects_non_scale_or_out_of_range_source_atomically():
    for clip, message in [
        (make_clip(NoteEvent(61, 0, 120, 90)), "must belong"),
        (make_clip(NoteEvent(127, 0, 120, 90)), "outside 0..127"),
    ]:
        try:
            harmonize_diatonic(clip, 2, "C", "major")
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError("invalid harmony was accepted")


def test_quantize_supports_quarter_eighth_and_sixteenth_grids():
    clip = make_clip(NoteEvent(60, 181, 120, 90))

    assert quantize(clip, "1/4").notes[0].start == 0
    assert quantize(clip, "1/8").notes[0].start == 240
    assert quantize(clip, "1/16").notes[0].start == 240


def test_quantize_uses_stable_half_up_rounding_and_preserves_normal_duration():
    clip = make_clip(NoteEvent(60, 120, 180, 90, mute=True))

    first = quantize(clip, "1/4")
    second = quantize(clip, "1/4")

    assert first == second
    assert first.notes[0] == NoteEvent(60, 0, 180, 90, mute=True)
    assert clip.notes[0].start == 120


def test_quantize_keeps_notes_inside_clip_and_truncates_only_at_boundary():
    clip = make_clip(NoteEvent(60, 1780, 140, 90), length_ticks=1920)

    result = quantize(clip, "1/4")

    assert result.notes[0].start == 1440
    assert result.notes[0].duration == 140
    assert result.notes[0].start + result.notes[0].duration <= result.length_ticks


def test_quantize_truncates_duration_when_later_start_reaches_clip_boundary():
    clip = make_clip(NoteEvent(60, 430, 70, 90), length_ticks=500)

    result = quantize(clip, "1/16")

    assert result.notes[0].start == 480
    assert result.notes[0].duration == 20


def test_humanize_is_repeatable_and_different_seeds_can_differ():
    clip = make_clip(
        NoteEvent(60, 240, 120, 90),
        NoteEvent(64, 720, 120, 90),
        NoteEvent(67, 1200, 120, 90),
    )

    assert humanize(clip, 42, 24, 8) == humanize(clip, 42, 24, 8)
    assert humanize(clip, 42, 24, 8) != humanize(clip, 43, 24, 8)


def test_humanize_clamps_timing_velocity_and_preserves_pitch_mute_and_input():
    original = (
        NoteEvent(60, 0, 240, 1, mute=True),
        NoteEvent(127, 1680, 240, 127),
    )
    clip = make_clip(*original)

    result = humanize(clip, 7, 96, 40)

    assert clip.notes == original
    assert [note.pitch for note in result.notes] == [60, 127]
    assert [note.mute for note in result.notes] == [True, False]
    assert all(1 <= note.velocity <= 127 for note in result.notes)
    assert all(0 <= note.start for note in result.notes)
    assert all(note.start + note.duration <= result.length_ticks for note in result.notes)
