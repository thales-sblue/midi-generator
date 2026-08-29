import pytest

from midi_generator.ableton import AbletonCommandError
from midi_generator.mcp.ableton_transform import transform_midi_clip_copy


def snapshot(track, scene, fingerprint, pitch=60):
    return {
        "track_index": track,
        "scene_index": scene,
        "clip_length_beats": 4.0,
        "notes": [
            {
                "pitch": pitch,
                "start_time": 0.5,
                "duration": 0.5,
                "velocity": 90,
                "mute": True,
            }
        ],
        "clip_fingerprint": fingerprint,
    }


class RecordingClient:
    def __init__(self, source=None, copy=None, duplicate_error=None, replace_error=None):
        self.source = source or snapshot(0, 0, "source")
        self.copy = copy or snapshot(0, 1, "copy")
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
            "clip_fingerprint": "transformed",
        }


def test_transform_flow_only_replaces_copy_and_uses_copy_fingerprint():
    client = RecordingClient()

    result = transform_midi_clip_copy(client, 0, 0, 0, 1, "transpose", semitones=12)

    assert [call[0] for call in client.calls] == ["get", "duplicate", "get", "replace"]
    assert client.calls[1] == ("duplicate", 0, 0, 0, 1, "source")
    replace = client.calls[-1]
    assert replace[1:4] == (0, 1, "copy")
    assert replace[4][0] == {
        "pitch": 72,
        "start_time": 0.5,
        "duration": 0.5,
        "velocity": 90,
        "mute": True,
    }
    assert not any(call[0] == "replace" and call[1:3] == (0, 0) for call in client.calls)
    assert result["source_clip_fingerprint"] == "source"
    assert result["target_clip_fingerprint"] == "transformed"


def test_retrograde_is_preflighted_and_applied_only_to_copy():
    client = RecordingClient()

    result = transform_midi_clip_copy(client, 0, 0, 0, 1, "retrograde")

    assert [call[0] for call in client.calls] == ["get", "duplicate", "get", "replace"]
    assert client.calls[-1][4][0]["start_time"] == 3.0
    assert client.source["notes"][0]["start_time"] == 0.5
    assert result["transform"] == "retrograde"


def test_invert_is_preflighted_and_applied_only_to_copy():
    client = RecordingClient()

    result = transform_midi_clip_copy(
        client, 0, 0, 0, 1, "invert", axis_pitch=64
    )

    assert [call[0] for call in client.calls] == ["get", "duplicate", "get", "replace"]
    assert client.calls[-1][4][0]["pitch"] == 68
    assert client.source["notes"][0]["pitch"] == 60
    assert result["transform"] == "invert"


def test_legato_is_preflighted_and_applied_only_to_copy():
    client = RecordingClient()

    result = transform_midi_clip_copy(client, 0, 0, 0, 1, "legato")

    assert [call[0] for call in client.calls] == ["get", "duplicate", "get", "replace"]
    assert client.calls[-1][4][0]["duration"] == 3.5
    assert client.source["notes"][0]["duration"] == 0.5
    assert result["transform"] == "legato"


def test_staccato_is_preflighted_and_applied_only_to_copy():
    client = RecordingClient()

    result = transform_midi_clip_copy(
        client, 0, 0, 0, 1, "staccato", max_duration=0.25
    )

    assert [call[0] for call in client.calls] == [
        "get",
        "duplicate",
        "get",
        "replace",
    ]
    assert client.calls[-1][4][0]["duration"] == 0.25
    assert client.source["notes"][0]["duration"] == 0.5
    assert result["transform"] == "staccato"


def test_constrain_to_scale_is_preflighted_and_applied_only_to_copy():
    client = RecordingClient(source=snapshot(0, 0, "source", pitch=61))

    result = transform_midi_clip_copy(
        client, 0, 0, 0, 1, "constrain_to_scale", root_note="C", scale="major"
    )

    assert [call[0] for call in client.calls] == ["get", "duplicate", "get", "replace"]
    assert client.calls[-1][4][0]["pitch"] == 60
    assert client.source["notes"][0]["pitch"] == 61
    assert result["transform"] == "constrain_to_scale"


def test_diatonic_transposition_is_preflighted_and_applied_only_to_copy():
    client = RecordingClient(source=snapshot(0, 0, "source", pitch=60))

    result = transform_midi_clip_copy(
        client,
        0,
        0,
        0,
        1,
        "transpose_diatonic",
        steps=2,
        root_note="C",
        scale="major",
    )

    assert [call[0] for call in client.calls] == ["get", "duplicate", "get", "replace"]
    assert client.calls[-1][4][0]["pitch"] == 64
    assert client.source["notes"][0]["pitch"] == 60
    assert result["transform"] == "transpose_diatonic"


def test_diatonic_harmony_adds_voice_only_to_protected_copy():
    client = RecordingClient(source=snapshot(0, 0, "source", pitch=60))

    result = transform_midi_clip_copy(
        client,
        0,
        0,
        0,
        1,
        "harmonize_diatonic",
        steps=2,
        root_note="C",
        scale="major",
    )

    assert [call[0] for call in client.calls] == [
        "get",
        "duplicate",
        "get",
        "replace",
    ]
    assert [note["pitch"] for note in client.calls[-1][4]] == [60, 64]
    assert client.source["notes"] == [
        {
            "pitch": 60,
            "start_time": 0.5,
            "duration": 0.5,
            "velocity": 90,
            "mute": True,
        }
    ]
    assert result["note_count"] == 2
    assert result["transform"] == "harmonize_diatonic"


def test_diatonic_harmony_rejects_foreign_pitch_before_duplicate():
    client = RecordingClient(source=snapshot(0, 0, "source", pitch=61))

    with pytest.raises(ValueError, match="must belong"):
        transform_midi_clip_copy(
            client,
            0,
            0,
            0,
            1,
            "harmonize_diatonic",
            steps=2,
            root_note="C",
            scale="major",
        )

    assert client.calls == [("get", 0, 0)]


def test_velocity_ramp_is_preflighted_and_applied_only_to_copy():
    source = snapshot(0, 0, "source")
    source["notes"].append(
        {
            "pitch": 64,
            "start_time": 2.5,
            "duration": 0.5,
            "velocity": 70,
            "mute": False,
        }
    )
    copy = snapshot(0, 1, "copy")
    copy["notes"].append(dict(source["notes"][1]))
    client = RecordingClient(source=source, copy=copy)

    result = transform_midi_clip_copy(
        client,
        0,
        0,
        0,
        1,
        "velocity_ramp",
        start_velocity=40,
        end_velocity=100,
    )

    assert [call[0] for call in client.calls] == [
        "get",
        "duplicate",
        "get",
        "replace",
    ]
    assert [note["velocity"] for note in client.calls[-1][4]] == [40, 100]
    assert [note["velocity"] for note in client.source["notes"]] == [90, 70]
    assert result["transform"] == "velocity_ramp"


@pytest.mark.parametrize(
    ("start_velocity", "end_velocity", "message"),
    [
        (None, 100, "velocity_ramp requires"),
        (0, 100, "start_velocity must be"),
        (40, 128, "end_velocity must be"),
        (True, 100, "start_velocity must be"),
    ],
)
def test_invalid_velocity_ramp_parameters_fail_before_reading_source(
    start_velocity, end_velocity, message
):
    client = RecordingClient()

    with pytest.raises(ValueError, match=message):
        transform_midi_clip_copy(
            client,
            0,
            0,
            0,
            1,
            "velocity_ramp",
            start_velocity=start_velocity,
            end_velocity=end_velocity,
        )

    assert client.calls == []


def test_missing_diatonic_harmony_parameters_fail_before_reading_source():
    client = RecordingClient()

    with pytest.raises(ValueError, match="harmonize_diatonic requires"):
        transform_midi_clip_copy(
            client,
            0,
            0,
            0,
            1,
            "harmonize_diatonic",
            root_note="C",
            scale="major",
        )

    assert client.calls == []


def test_missing_tonality_fails_before_reading_source():
    client = RecordingClient()

    with pytest.raises(ValueError, match="constrain_to_scale requires"):
        transform_midi_clip_copy(client, 0, 0, 0, 1, "constrain_to_scale", root_note="C")

    assert client.calls == []


def test_missing_staccato_duration_fails_before_reading_source():
    client = RecordingClient()

    with pytest.raises(ValueError, match="staccato requires max_duration"):
        transform_midi_clip_copy(client, 0, 0, 0, 1, "staccato")

    assert client.calls == []


def test_sub_tick_staccato_duration_fails_before_reading_source():
    client = RecordingClient()

    with pytest.raises(ValueError, match="at least one tick"):
        transform_midi_clip_copy(
            client, 0, 0, 0, 1, "staccato", max_duration=0.001
        )

    assert client.calls == []


def test_target_must_be_empty_and_bridge_error_is_propagated():
    error = AbletonCommandError("TARGET_CLIP_SLOT_NOT_EMPTY", "occupied")
    client = RecordingClient(duplicate_error=error)

    with pytest.raises(AbletonCommandError) as caught:
        transform_midi_clip_copy(client, 0, 0, 0, 1, "quantize", grid="1/16")

    assert caught.value.code == "TARGET_CLIP_SLOT_NOT_EMPTY"
    assert not any(call[0] == "replace" for call in client.calls)


def test_invalid_transpose_fails_before_duplicate():
    client = RecordingClient(source=snapshot(0, 0, "source", pitch=127))

    with pytest.raises(ValueError, match="outside 0..127"):
        transform_midi_clip_copy(client, 0, 0, 0, 1, "transpose", semitones=1)

    assert client.calls == [("get", 0, 0)]


def test_invalid_inversion_fails_before_duplicate():
    client = RecordingClient(source=snapshot(0, 0, "source", pitch=127))

    with pytest.raises(ValueError, match="outside 0..127"):
        transform_midi_clip_copy(
            client, 0, 0, 0, 1, "invert", axis_pitch=60
        )

    assert client.calls == [("get", 0, 0)]


def test_invalid_parameters_fail_even_before_reading_source():
    client = RecordingClient()

    with pytest.raises(ValueError, match="quantize requires grid"):
        transform_midi_clip_copy(client, 0, 0, 0, 1, "quantize")

    assert client.calls == []


def test_missing_inversion_axis_fails_before_reading_source():
    client = RecordingClient()

    with pytest.raises(ValueError, match="invert requires axis_pitch"):
        transform_midi_clip_copy(client, 0, 0, 0, 1, "invert")

    assert client.calls == []


def test_clip_changed_from_copy_replace_is_propagated_and_source_untouched():
    error = AbletonCommandError("CLIP_CHANGED", "changed")
    client = RecordingClient(replace_error=error)

    with pytest.raises(AbletonCommandError) as caught:
        transform_midi_clip_copy(
            client,
            0,
            0,
            0,
            1,
            "humanize",
            seed=42,
            max_timing_shift=0.05,
            max_velocity_delta=5,
        )

    assert caught.value.code == "CLIP_CHANGED"
    assert client.calls[-1][1:4] == (0, 1, "copy")
    assert not any(call[0] == "replace" and call[1:3] == (0, 0) for call in client.calls)


class SourceChangingClient(RecordingClient):
    def __init__(self):
        super().__init__()
        self.target_created = False

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
        self.source = snapshot(0, 0, "source-B", pitch=61)
        if expected_source_fingerprint != self.source["clip_fingerprint"]:
            raise AbletonCommandError("CLIP_CHANGED", "source changed")
        self.target_created = True
        return {"duplicated": True}


def test_source_change_between_read_and_protected_duplicate_stops_pipeline():
    client = SourceChangingClient()

    with pytest.raises(AbletonCommandError) as caught:
        transform_midi_clip_copy(
            client, 0, 0, 0, 1, "transpose", semitones=12
        )

    assert caught.value.code == "CLIP_CHANGED"
    assert client.calls == [
        ("get", 0, 0),
        ("duplicate", 0, 0, 0, 1, "source"),
    ]
    assert client.source["clip_fingerprint"] == "source-B"
    assert client.source["notes"][0]["pitch"] == 61
    assert client.target_created is False
    assert not any(call[0] == "replace" for call in client.calls)
