from midi_generator.domain import NoteEvent
from midi_generator.transformations import (
    EditableMidiClip,
    humanize,
    quantize,
    retrograde,
    transpose,
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
