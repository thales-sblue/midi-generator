"""Non-destructive MCP flow for the bass-line and chord-bed generators."""

import pytest

from midi_generator.ableton import AbletonCommandError
from midi_generator.generation.drums import KICK_PITCH
from midi_generator.mcp.ableton_transform import (
    create_bass_line_midi_clip_copy,
    create_chord_bed_midi_clip_copy,
    create_kick_midi_clip_copy,
)


def bass_source(fingerprint="source", length_beats=4.0, pitches=(48, 50, 52, 53)):
    """A one-bar 4/4 clip with one sounding note on each beat."""
    return {
        "track_index": 0,
        "scene_index": 0,
        "clip_length_beats": length_beats,
        "notes": [
            {
                "pitch": pitch,
                "start_time": float(beat),
                "duration": 1.0,
                "velocity": 100,
                "mute": False,
            }
            for beat, pitch in enumerate(pitches)
        ],
        "clip_fingerprint": fingerprint,
    }


def muted_source(fingerprint="source"):
    snapshot = bass_source(fingerprint)
    for note in snapshot["notes"]:
        note["mute"] = True
    return snapshot


def copy_snapshot(fingerprint="copy", length_beats=4.0):
    return {
        "track_index": 0,
        "scene_index": 1,
        "clip_length_beats": length_beats,
        "notes": [
            {
                "pitch": 60,
                "start_time": 0.0,
                "duration": 1.0,
                "velocity": 90,
                "mute": False,
            }
        ],
        "clip_fingerprint": fingerprint,
    }


class RecordingClient:
    def __init__(self, source=None, copy=None, duplicate_error=None, replace_error=None):
        self.source = source or bass_source()
        self.copy = copy or copy_snapshot()
        self.duplicate_error = duplicate_error
        self.replace_error = replace_error
        self.calls = []

    def get_midi_clip(self, track, scene):
        self.calls.append(("get", track, scene))
        return self.source if (track, scene) == (0, 0) else self.copy

    def duplicate_midi_clip(
        self,
        source_track,
        source_scene,
        target_track,
        target_scene,
        expected_source_fingerprint=None,
    ):
        self.calls.append(
            (
                "duplicate",
                source_track,
                source_scene,
                target_track,
                target_scene,
                expected_source_fingerprint,
            )
        )
        if self.duplicate_error:
            raise self.duplicate_error
        return {"duplicated": True}

    def replace_midi_clip_notes(self, track, scene, fingerprint, notes):
        self.calls.append(("replace", track, scene, fingerprint, notes))
        if self.replace_error:
            raise self.replace_error
        return {
            "replaced": True,
            "clip_length_beats": 4.0,
            "note_count": len(notes),
            "clip_fingerprint": "generated",
        }


def replaced_notes(client):
    return client.calls[-1][4]


# --- bass line ---------------------------------------------------------------


def test_bass_line_generates_and_replaces_only_protected_copy():
    client = RecordingClient()

    result = create_bass_line_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert [call[0] for call in client.calls] == [
        "get",
        "duplicate",
        "get",
        "replace",
    ]
    assert client.calls[1] == ("duplicate", 0, 0, 0, 1, "source")
    assert client.calls[-1][1:4] == (0, 1, "copy")
    assert [note["pitch"] for note in replaced_notes(client)] == [48, 50, 52, 53]
    assert all(not note["mute"] for note in replaced_notes(client))
    assert result["generated"] is True
    assert result["role"] == "bass_line"
    assert result["source_clip_fingerprint"] == "source"
    assert result["target_clip_fingerprint"] == "generated"
    assert result["bars"] == 1
    assert result["root_note"] == "C"
    assert result["scale"] == "major"
    assert result["seed"] == 7
    assert result["velocity"] == 96
    assert result["note_grouping"] == "per_window"


def test_bass_line_never_touches_the_source_clip():
    original = bass_source()
    client = RecordingClient(source=bass_source())

    create_bass_line_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert client.source == original
    assert not any(
        call[0] == "replace" and call[1:3] == (0, 0) for call in client.calls
    )


def test_bass_line_is_deterministic_for_same_inputs():
    first = RecordingClient(source=bass_source())
    second = RecordingClient(source=bass_source())

    create_bass_line_midi_clip_copy(first, 0, 0, 0, 1, 120, "C", "major", 3)
    create_bass_line_midi_clip_copy(second, 0, 0, 0, 1, 120, "C", "major", 3)

    assert replaced_notes(first) == replaced_notes(second)


def test_bass_line_forwards_velocity_sustain_and_octave():
    client = RecordingClient(
        source=bass_source(pitches=(48, 48, 48, 48))
    )

    result = create_bass_line_midi_clip_copy(
        client,
        0,
        0,
        0,
        1,
        120,
        "C",
        "major",
        7,
        velocity=55,
        sustain=True,
        octave=2,
    )

    notes = replaced_notes(client)
    assert len(notes) == 1
    assert notes[0]["velocity"] == 55
    assert notes[0]["pitch"] == 36
    assert notes[0]["duration"] == 4.0
    assert result["velocity"] == 55
    assert result["sustain"] is True
    assert result["octave"] == 2
    assert result["note_grouping"] == "sustained"
    assert result["octave_offset_semitones"] == -12


def test_bass_line_forwards_segment_beats():
    client = RecordingClient()

    create_bass_line_midi_clip_copy(
        client, 0, 0, 0, 1, 120, "C", "major", 7, segment_beats=2
    )

    # Two 2-beat windows, lowest pitch of each: 48 then 52.
    assert [note["pitch"] for note in replaced_notes(client)] == [48, 52]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"velocity": 0}, "velocity must be"),
        ({"sustain": "yes"}, "sustain must be a boolean"),
        ({"segment_beats": 0}, "segment_beats must be a positive integer"),
        ({"octave": 42}, "octave must be an integer"),
    ],
)
def test_bass_line_rejects_invalid_generation_parameters_before_duplicate(
    kwargs, message
):
    client = RecordingClient()

    with pytest.raises(ValueError, match=message):
        create_bass_line_midi_clip_copy(
            client, 0, 0, 0, 1, 120, "C", "major", 7, **kwargs
        )

    assert client.calls == [("get", 0, 0)]


def test_bass_line_rejects_same_source_and_target_before_any_read():
    client = RecordingClient()

    with pytest.raises(ValueError, match="must be different"):
        create_bass_line_midi_clip_copy(client, 0, 0, 0, 0, 120, "C", "major", 7)

    assert client.calls == []


def test_bass_line_requires_whole_four_four_bars_before_duplicate():
    client = RecordingClient(
        source=bass_source(length_beats=3.0, pitches=(48, 50, 52))
    )

    with pytest.raises(ValueError, match="whole number of 4/4 bars"):
        create_bass_line_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert client.calls == [("get", 0, 0)]


def test_bass_line_rejects_fully_muted_source_before_duplicate():
    client = RecordingClient(source=muted_source())

    with pytest.raises(ValueError, match="at least one sounding note"):
        create_bass_line_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert client.calls == [("get", 0, 0)]


def test_bass_line_propagates_clip_changed_from_duplicate():
    error = AbletonCommandError("CLIP_CHANGED", "source changed")
    client = RecordingClient(duplicate_error=error)

    with pytest.raises(AbletonCommandError) as caught:
        create_bass_line_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert caught.value.code == "CLIP_CHANGED"
    assert [call[0] for call in client.calls] == ["get", "duplicate"]
    assert not any(call[0] == "replace" for call in client.calls)


def test_bass_line_propagates_bridge_replace_error_without_touching_source():
    error = AbletonCommandError("CLIP_CHANGED", "copy changed")
    client = RecordingClient(replace_error=error)

    with pytest.raises(AbletonCommandError) as caught:
        create_bass_line_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert caught.value.code == "CLIP_CHANGED"
    assert client.calls[-1][1:4] == (0, 1, "copy")
    assert not any(
        call[0] == "replace" and call[1:3] == (0, 0) for call in client.calls
    )


# --- chord bed -------------------------------------------------------------


def test_chord_bed_generates_stacked_triads_only_in_protected_copy():
    client = RecordingClient()

    result = create_chord_bed_midi_clip_copy(
        client, 0, 0, 0, 1, 120, "C", "major", 7
    )

    assert [call[0] for call in client.calls] == [
        "get",
        "duplicate",
        "get",
        "replace",
    ]
    assert client.calls[1] == ("duplicate", 0, 0, 0, 1, "source")
    # First sounding window: bass 48 (C) -> C E G triad.
    assert [note["pitch"] for note in replaced_notes(client)][:3] == [48, 52, 55]
    assert result["generated"] is True
    assert result["role"] == "chord_bed"
    assert result["chord_size"] == 3
    assert result["chord_count"] == 4
    assert result["voicing"] == "stacked_scale_degrees"
    assert result["velocity"] == 80
    assert result["source_clip_fingerprint"] == "source"
    assert result["target_clip_fingerprint"] == "generated"


def test_chord_bed_never_touches_the_source_clip():
    original = bass_source()
    client = RecordingClient(source=bass_source())

    create_chord_bed_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert client.source == original
    assert not any(
        call[0] == "replace" and call[1:3] == (0, 0) for call in client.calls
    )


def test_chord_bed_is_deterministic_for_same_inputs():
    first = RecordingClient(source=bass_source())
    second = RecordingClient(source=bass_source())

    create_chord_bed_midi_clip_copy(first, 0, 0, 0, 1, 120, "C", "major", 11)
    create_chord_bed_midi_clip_copy(second, 0, 0, 0, 1, 120, "C", "major", 11)

    assert replaced_notes(first) == replaced_notes(second)


def test_chord_bed_forwards_chord_size_velocity_sustain_and_octave():
    client = RecordingClient(source=bass_source(pitches=(48, 48, 48, 48)))

    result = create_chord_bed_midi_clip_copy(
        client,
        0,
        0,
        0,
        1,
        120,
        "C",
        "major",
        7,
        chord_size=4,
        velocity=64,
        sustain=True,
        octave=3,
    )

    notes = replaced_notes(client)
    # One sustained C-major seventh chord: C E G B anchored to octave 3.
    assert len(notes) == 4
    assert [note["pitch"] for note in notes] == [48, 52, 55, 59]
    assert all(note["velocity"] == 64 for note in notes)
    assert all(note["duration"] == 4.0 for note in notes)
    assert result["chord_size"] == 4
    assert result["velocity"] == 64
    assert result["sustain"] is True
    assert result["octave"] == 3
    assert result["note_grouping"] == "sustained"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"chord_size": 1}, "chord_size must be"),
        ({"chord_size": 6}, "chord_size must be"),
        ({"velocity": 200}, "velocity must be"),
        ({"segment_beats": -1}, "segment_beats must be a positive integer"),
    ],
)
def test_chord_bed_rejects_invalid_generation_parameters_before_duplicate(
    kwargs, message
):
    client = RecordingClient()

    with pytest.raises(ValueError, match=message):
        create_chord_bed_midi_clip_copy(
            client, 0, 0, 0, 1, 120, "C", "major", 7, **kwargs
        )

    assert client.calls == [("get", 0, 0)]


def test_chord_bed_rejects_same_source_and_target_before_any_read():
    client = RecordingClient()

    with pytest.raises(ValueError, match="must be different"):
        create_chord_bed_midi_clip_copy(client, 0, 0, 0, 0, 120, "C", "major", 7)

    assert client.calls == []


def test_chord_bed_propagates_clip_changed_from_duplicate():
    error = AbletonCommandError("CLIP_CHANGED", "source changed")
    client = RecordingClient(duplicate_error=error)

    with pytest.raises(AbletonCommandError) as caught:
        create_chord_bed_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert caught.value.code == "CLIP_CHANGED"
    assert not any(call[0] == "replace" for call in client.calls)


# --- kick ----------------------------------------------------------------------


def test_kick_generates_and_replaces_only_protected_copy():
    client = RecordingClient()

    result = create_kick_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert [call[0] for call in client.calls] == [
        "get",
        "duplicate",
        "get",
        "replace",
    ]
    assert client.calls[1] == ("duplicate", 0, 0, 0, 1, "source")
    assert client.calls[-1][1:4] == (0, 1, "copy")
    # One kick on each of the four sounding onsets, all at KICK_PITCH.
    assert [note["pitch"] for note in replaced_notes(client)] == [KICK_PITCH] * 4
    assert all(not note["mute"] for note in replaced_notes(client))
    assert result["generated"] is True
    assert result["role"] == "kick"
    assert result["source_clip_fingerprint"] == "source"
    assert result["target_clip_fingerprint"] == "generated"
    assert result["bars"] == 1
    assert result["root_note"] == "C"
    assert result["scale"] == "major"
    assert result["seed"] == 7
    assert result["velocity"] == 100
    assert result["onset_count"] == 4
    assert result["kick_pitch"] == KICK_PITCH
    assert result["reference_length_ticks"] == 1920


def test_kick_never_touches_the_source_clip():
    original = bass_source()
    client = RecordingClient(source=bass_source())

    create_kick_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert client.source == original
    assert not any(
        call[0] == "replace" and call[1:3] == (0, 0) for call in client.calls
    )


def test_kick_is_deterministic_for_same_inputs():
    first = RecordingClient(source=bass_source())
    second = RecordingClient(source=bass_source())

    create_kick_midi_clip_copy(first, 0, 0, 0, 1, 120, "C", "major", 3)
    create_kick_midi_clip_copy(second, 0, 0, 0, 1, 120, "C", "major", 3)

    assert replaced_notes(first) == replaced_notes(second)


def test_kick_seed_only_travels_to_metadata_not_content():
    one = RecordingClient(source=bass_source())
    other = RecordingClient(source=bass_source())

    result_one = create_kick_midi_clip_copy(one, 0, 0, 0, 1, 120, "C", "major", 1)
    result_other = create_kick_midi_clip_copy(
        other, 0, 0, 0, 1, 120, "C", "major", 999
    )

    assert replaced_notes(one) == replaced_notes(other)
    assert result_one["seed"] == 1
    assert result_other["seed"] == 999


def test_kick_forwards_velocity_to_generator():
    client = RecordingClient()

    result = create_kick_midi_clip_copy(
        client, 0, 0, 0, 1, 120, "C", "major", 7, velocity=55
    )

    notes = replaced_notes(client)
    assert notes and all(note["velocity"] == 55 for note in notes)
    assert result["velocity"] == 55


def test_kick_ignores_request_key_for_content():
    c_major = RecordingClient(source=bass_source())
    f_minor = RecordingClient(source=bass_source())

    create_kick_midi_clip_copy(c_major, 0, 0, 0, 1, 120, "C", "major", 7)
    create_kick_midi_clip_copy(f_minor, 0, 0, 0, 1, 120, "F", "minor", 7)

    assert replaced_notes(c_major) == replaced_notes(f_minor)


def test_kick_rejects_out_of_range_velocity_before_duplicate():
    client = RecordingClient()

    with pytest.raises(ValueError, match="velocity must be"):
        create_kick_midi_clip_copy(
            client, 0, 0, 0, 1, 120, "C", "major", 7, velocity=0
        )

    assert client.calls == [("get", 0, 0)]


def test_kick_rejects_same_source_and_target_before_any_read():
    client = RecordingClient()

    with pytest.raises(ValueError, match="must be different"):
        create_kick_midi_clip_copy(client, 0, 0, 0, 0, 120, "C", "major", 7)

    assert client.calls == []


def test_kick_requires_whole_four_four_bars_before_duplicate():
    client = RecordingClient(
        source=bass_source(length_beats=3.0, pitches=(48, 50, 52))
    )

    with pytest.raises(ValueError, match="whole number of 4/4 bars"):
        create_kick_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert client.calls == [("get", 0, 0)]


def test_kick_rejects_fully_muted_source_before_duplicate():
    client = RecordingClient(source=muted_source())

    with pytest.raises(ValueError, match="at least one sounding note"):
        create_kick_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert client.calls == [("get", 0, 0)]


def test_kick_propagates_clip_changed_from_duplicate():
    error = AbletonCommandError("CLIP_CHANGED", "source changed")
    client = RecordingClient(duplicate_error=error)

    with pytest.raises(AbletonCommandError) as caught:
        create_kick_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert caught.value.code == "CLIP_CHANGED"
    assert [call[0] for call in client.calls] == ["get", "duplicate"]
    assert not any(call[0] == "replace" for call in client.calls)


def test_kick_propagates_bridge_replace_error_without_touching_source():
    error = AbletonCommandError("CLIP_CHANGED", "copy changed")
    client = RecordingClient(replace_error=error)

    with pytest.raises(AbletonCommandError) as caught:
        create_kick_midi_clip_copy(client, 0, 0, 0, 1, 120, "C", "major", 7)

    assert caught.value.code == "CLIP_CHANGED"
    assert client.calls[-1][1:4] == (0, 1, "copy")
    assert not any(
        call[0] == "replace" and call[1:3] == (0, 0) for call in client.calls
    )
