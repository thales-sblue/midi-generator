import pytest

from midi_generator.integration import (
    ableton_snapshot_to_clip,
    beats_to_ticks,
    clip_notes_to_ableton,
)


def test_snapshot_round_trip_uses_480_ticks_and_preserves_note_properties():
    snapshot = {
        "clip_length_beats": 4.0,
        "notes": [
            {
                "pitch": 64,
                "start_time": 0.25,
                "duration": 0.5,
                "velocity": 91,
                "mute": True,
            }
        ],
    }

    clip = ableton_snapshot_to_clip(snapshot)

    assert clip.length_ticks == 1920
    assert clip.notes[0].start == 120
    assert clip.notes[0].duration == 240
    assert clip_notes_to_ableton(clip) == snapshot["notes"]


def test_beat_conversion_uses_explicit_decimal_half_up_rounding():
    assert beats_to_ticks(0.001) == 0
    assert beats_to_ticks("0.0010416666666666667") == 1
    assert beats_to_ticks(0.05) == 24


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, True])
def test_beat_conversion_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        beats_to_ticks(value)
