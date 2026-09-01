"""End-to-end read-back verification harness for the pending bridge gate."""

import pytest

from ableton_remote_script.MidiGeneratorBridge.bridge_core import (
    BridgeCommandError,
    BridgeDispatcher,
)
from midi_generator.ableton import AbletonCommandError
from midi_generator.mcp.verification import (
    verify_contextual_roundtrip,
    verify_transform_roundtrip,
)


class FakeNote:
    def __init__(self, pitch, start_time, duration, velocity, mute=False):
        self.pitch = pitch
        self.start_time = start_time
        self.duration = duration
        self.velocity = velocity
        self.mute = mute


class FakeClip:
    def __init__(self, notes=None, length=16.0, is_midi_clip=True):
        self.notes = list(notes or [])
        self.length = length
        self.name = "Melody"
        self.looping = True
        self.is_midi_clip = is_midi_clip
        self.remove_calls = 0

    def add_new_notes(self, notes):
        self.notes.extend(
            FakeNote(**note) if isinstance(note, dict) else note for note in notes
        )

    def get_notes_extended(self, _p, _ps, _t, _ts):
        return tuple(self.notes)

    def remove_notes_extended(self, _p, _ps, _t, _ts):
        self.remove_calls += 1
        self.notes = []


class FakeClipSlot:
    def __init__(self, has_clip=False):
        self.has_clip = has_clip
        self.clip = FakeClip() if has_clip else None

    def create_clip(self, length):
        self.has_clip = True
        self.clip = FakeClip(notes=[], length=length)


class FakeTrack:
    def __init__(self, slots):
        self.name = "MIDI"
        self.has_midi_input = True
        self.clip_slots = slots


class FakeSong:
    def __init__(self, track):
        self.tracks = [track]
        self.scenes = [type("S", (), {"name": "s"})() for _ in track.clip_slots]


class FakeLiveContext:
    def __init__(self, track):
        self._song = FakeSong(track)

    def application(self):
        return type("A", (), {"get_version_string": lambda self: "12.4.5"})()

    def song(self):
        return self._song


class DispatcherClient:
    """Drives the real bridge dispatcher against an in-memory Live context."""

    def __init__(self, context):
        self._dispatcher = BridgeDispatcher(context)
        self._counter = 0

    def _dispatch(self, command, params):
        self._counter += 1
        try:
            response = self._dispatcher.dispatch(
                {"request_id": str(self._counter), "command": command, "params": params}
            )
        except BridgeCommandError as error:
            # The real AbletonClient never leaks BridgeCommandError.
            raise AbletonCommandError(error.code, error.message) from error
        return response["result"]

    def get_midi_clip(self, track_index, scene_index):
        return self._dispatch(
            "get_midi_clip",
            {"track_index": track_index, "scene_index": scene_index},
        )

    def duplicate_midi_clip(
        self,
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        expected_source_fingerprint=None,
    ):
        params = {
            "source_track_index": source_track_index,
            "source_scene_index": source_scene_index,
            "target_track_index": target_track_index,
            "target_scene_index": target_scene_index,
        }
        if expected_source_fingerprint is not None:
            params["expected_source_fingerprint"] = expected_source_fingerprint
        return self._dispatch("duplicate_midi_clip", params)

    def replace_midi_clip_notes(
        self, track_index, scene_index, expected_fingerprint, notes
    ):
        return self._dispatch(
            "replace_midi_clip_notes",
            {
                "track_index": track_index,
                "scene_index": scene_index,
                "expected_fingerprint": expected_fingerprint,
                "notes": notes,
            },
        )


def context_with_source(notes, empty_slots=1):
    fresh = [
        FakeNote(n.pitch, n.start_time, n.duration, n.velocity, n.mute) for n in notes
    ]
    slots = [FakeClipSlot(has_clip=True)]
    slots[0].clip = FakeClip(notes=fresh, length=16.0)
    slots.extend(FakeClipSlot() for _ in range(empty_slots))
    return FakeLiveContext(FakeTrack(slots))


C_MAJOR_SCALE = [
    FakeNote(60, 0.0, 1.0, 80),
    FakeNote(64, 1.0, 1.0, 90),
    FakeNote(67, 2.0, 1.0, 100),
    FakeNote(72, 3.0, 1.0, 110),
]


def test_transform_roundtrip_passes_when_target_matches_and_source_preserved():
    client = DispatcherClient(context_with_source(C_MAJOR_SCALE))

    report = verify_transform_roundtrip(
        client,
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        transform="transpose_diatonic",
        steps=1,
        root_note="C",
        scale="major",
    )

    assert report.operation == "transpose_diatonic"
    assert report.passed is True
    assert {check.name: check.passed for check in report.checks} == {
        "orchestration_succeeded": True,
        "source_preserved": True,
        "target_matches_expected": True,
        "reported_fingerprint_matches_readback": True,
    }
    assert report.evidence["expected_note_count"] == 4
    assert report.evidence["target_note_count"] == 4


def test_transform_roundtrip_reports_source_mutation_as_failure():
    context = context_with_source(C_MAJOR_SCALE)
    client = DispatcherClient(context)

    class TamperingClient(DispatcherClient):
        def get_midi_clip(self, track_index, scene_index):
            result = super().get_midi_clip(track_index, scene_index)
            if (track_index, scene_index) == (0, 0):
                context.song().tracks[0].clip_slots[0].clip.notes[0].pitch += 1
            return result

    report = verify_transform_roundtrip(
        TamperingClient(context),
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        transform="constrain_to_scale",
        root_note="C",
        scale="major",
    )

    assert report.passed is False
    assert report.checks_by_name["source_preserved"].passed is False


def test_transform_roundtrip_flags_structural_mismatch(monkeypatch):
    client = DispatcherClient(context_with_source(C_MAJOR_SCALE))

    import midi_generator.mcp.verification as verification

    real_apply = verification._apply_transform

    def wrong_expectation(clip, transform, parameters):
        result = real_apply(clip, transform, parameters)
        from dataclasses import replace

        return replace(
            result,
            notes=tuple(replace(n, pitch=n.pitch + 5) for n in result.notes),
        )

    monkeypatch.setattr(verification, "_apply_transform", wrong_expectation)

    report = verify_transform_roundtrip(
        client,
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        transform="transpose",
        semitones=2,
    )

    assert report.passed is False
    assert report.checks_by_name["target_matches_expected"].passed is False
    assert report.evidence["first_note_diff"] is not None


def test_transform_roundtrip_captures_orchestration_error():
    client = DispatcherClient(context_with_source([FakeNote(61, 0.0, 1.0, 80)]))

    report = verify_transform_roundtrip(
        client,
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        transform="harmonize_diatonic",
        steps=2,
        root_note="C",
        scale="major",
    )

    assert report.passed is False
    assert report.checks_by_name["orchestration_succeeded"].passed is False
    assert "scale" in report.checks_by_name["orchestration_succeeded"].detail


def test_harmonize_roundtrip_preserves_original_voice_and_adds_one():
    client = DispatcherClient(context_with_source(C_MAJOR_SCALE))

    report = verify_transform_roundtrip(
        client,
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        transform="harmonize_diatonic",
        steps=2,
        root_note="C",
        scale="major",
    )

    assert report.passed is True
    assert report.evidence["target_note_count"] == 8


def test_velocity_ramp_roundtrip_passes():
    client = DispatcherClient(context_with_source(C_MAJOR_SCALE))

    report = verify_transform_roundtrip(
        client,
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        transform="velocity_ramp",
        start_velocity=40,
        end_velocity=120,
    )

    assert report.passed is True
    assert report.checks_by_name["target_matches_expected"].passed is True


def test_contextual_roundtrip_passes_and_is_non_destructive():
    client = DispatcherClient(context_with_source(C_MAJOR_SCALE))

    report = verify_contextual_roundtrip(
        client,
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        bpm=120,
        root_note="C",
        scale="major",
        seed=42,
    )

    assert report.operation == "create_contextual_variation_from_ableton_clip"
    assert report.passed is True
    assert report.checks_by_name["source_preserved"].passed is True
    assert report.checks_by_name["target_matches_expected"].passed is True


def test_report_serializes_to_plain_dict():
    client = DispatcherClient(context_with_source(C_MAJOR_SCALE))

    report = verify_transform_roundtrip(
        client,
        source_track_index=0,
        source_scene_index=0,
        target_track_index=0,
        target_scene_index=1,
        transform="retrograde",
    )

    payload = report.as_dict()
    assert payload["operation"] == "retrograde"
    assert payload["passed"] is True
    assert isinstance(payload["checks"], list)
    assert payload["checks"][0]["name"] == "orchestration_succeeded"
