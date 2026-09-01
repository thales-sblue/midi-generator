import pytest

from midi_generator.domain.music_theory import (
    nearest_scale_pitch,
    scale_pitch_classes,
    scale_pitches,
)


def test_scale_pitch_classes_of_c_major():
    assert scale_pitch_classes("C", "major") == frozenset({0, 2, 4, 5, 7, 9, 11})


def test_scale_pitch_classes_normalizes_case_and_enharmonics():
    assert scale_pitch_classes("db", "MAJOR") == scale_pitch_classes("C#", "major")
    assert scale_pitch_classes("a", "minor") == scale_pitch_classes("C", "major")


def test_scale_pitch_classes_of_fsharp_minor():
    # F# natural minor: F# G# A B C# D E
    assert scale_pitch_classes("F#", "minor") == frozenset({1, 2, 4, 6, 8, 9, 11})


@pytest.mark.parametrize(
    ("root_note", "scale", "message"),
    [
        ("H", "major", "root_note must be one of"),
        (5, "major", "root_note must be one of"),
        ("C", "wurlitzer", "scale must be one of"),
        ("C", None, "scale must be one of"),
    ],
)
def test_scale_pitch_classes_rejects_unknown_names(root_note, scale, message):
    with pytest.raises(ValueError, match=message):
        scale_pitch_classes(root_note, scale)


def test_scale_pitches_are_ascending_in_range_and_in_scale():
    pitches = scale_pitches("C", "major")
    allowed = scale_pitch_classes("C", "major")

    assert pitches == tuple(sorted(pitches))
    assert pitches[0] == 0
    assert pitches[-1] == 127
    assert all(0 <= pitch <= 127 for pitch in pitches)
    assert all(pitch % 12 in allowed for pitch in pitches)
    assert len(pitches) == sum(1 for pitch in range(128) if pitch % 12 in allowed)


def test_scale_pitches_validates_names():
    with pytest.raises(ValueError, match="scale must be one of"):
        scale_pitches("C", "bogus")


def test_nearest_scale_pitch_keeps_a_pitch_already_in_scale():
    allowed = scale_pitch_classes("C", "major")

    assert nearest_scale_pitch(60, allowed) == 60
    assert nearest_scale_pitch(67, allowed) == 67


def test_nearest_scale_pitch_breaks_ties_downward():
    allowed = scale_pitch_classes("C", "major")

    assert nearest_scale_pitch(61, allowed) == 60  # C# -> C, not D
    assert nearest_scale_pitch(66, allowed) == 65  # F# -> F, not G


def test_nearest_scale_pitch_stays_within_midi_range_near_boundaries():
    only_c = frozenset({0})
    only_b = frozenset({11})

    assert nearest_scale_pitch(1, only_c) == 0
    assert nearest_scale_pitch(127, only_c) == 120  # cannot go above 127
    assert nearest_scale_pitch(0, only_b) == 11  # cannot go below 0
