from pathlib import Path
import queue
import threading

import pytest

from ableton_remote_script.MidiGeneratorBridge.bridge_core import (
    BridgeCommandError,
    BridgeDispatcher,
    payload_to_clip_data,
)
from ableton_remote_script.MidiGeneratorBridge.socket_server import BridgeSocketServer
from midi_generator.ableton import AbletonClient
from midi_generator.ableton.installer import install_remote_script
from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import composition_to_payload


def make_payload():
    return composition_to_payload(
        generate_plan(MelodyRequest(120, "C", "minor", 4, 42))
    )


class FakeApplication:
    def get_version_string(self):
        return "12.4.3"


class FakeClip:
    def __init__(self):
        self.added = None

    def add_new_notes(self, notes):
        self.added = notes


class FakeClipSlot:
    def __init__(self, has_clip=False):
        self.has_clip = has_clip
        self.clip = FakeClip()
        self.created_length = None

    def create_clip(self, length):
        self.created_length = length
        self.has_clip = True


class FakeTrack:
    def __init__(self, name="MIDI", has_midi_input=True, has_clip=False):
        self.name = name
        self.has_midi_input = has_midi_input
        self.clip_slots = [FakeClipSlot(has_clip=has_clip)]


class FakeScene:
    name = "Scene 1"


class FakeSong:
    def __init__(self, track=None):
        self.tracks = [track or FakeTrack()]
        self.scenes = [FakeScene()]


class FakeLiveContext:
    def __init__(self, track=None):
        self._song = FakeSong(track)

    def application(self):
        return FakeApplication()

    def song(self):
        return self._song


def test_payload_converts_ticks_and_notes_to_live_beats():
    payload = make_payload()

    converted = payload_to_clip_data(payload)

    assert converted["clip_length_beats"] == 16.0
    assert converted["notes"] == [
        {
            "pitch": note["pitch"],
            "start_time": note["start"] / payload["ticks_per_beat"],
            "duration": note["duration"] / payload["ticks_per_beat"],
            "velocity": note["velocity"],
            "mute": False,
        }
        for note in payload["notes"]
    ]


def test_payload_conversion_does_not_hardcode_ticks_per_beat():
    payload = make_payload()
    payload["ticks_per_beat"] = 960
    payload["total_duration_ticks"] = 1920
    payload["notes"] = [
        {"pitch": 60, "start": 960, "duration": 480, "velocity": 90}
    ]

    converted = payload_to_clip_data(payload)

    assert converted["clip_length_beats"] == 2.0
    assert converted["notes"][0]["start_time"] == 1.0
    assert converted["notes"][0]["duration"] == 0.5


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schema_version", 2, "UNSUPPORTED_SCHEMA"),
        ("time_signature", "3/4", "UNSUPPORTED_TIME_SIGNATURE"),
        ("ticks_per_beat", 0, "INVALID_PAYLOAD"),
    ],
)
def test_bridge_rejects_unsupported_payload(field, value, code):
    payload = make_payload()
    payload[field] = value

    with pytest.raises(BridgeCommandError) as caught:
        payload_to_clip_data(payload)

    assert caught.value.code == code


def test_dispatcher_ping_and_minimal_session_state():
    dispatcher = BridgeDispatcher(FakeLiveContext())

    ping = dispatcher.dispatch({"request_id": "1", "command": "ping", "params": {}})
    session = dispatcher.dispatch(
        {"request_id": "2", "command": "get_session_state", "params": {}}
    )

    assert ping["result"] == {
        "application": "Ableton Live",
        "bridge": "MidiGeneratorBridge",
        "version": "12.4.3",
    }
    assert session["result"] == {
        "tracks": [{"index": 0, "name": "MIDI", "can_hold_midi": True}],
        "scenes": [{"index": 0, "name": "Scene 1"}],
    }


def test_dispatcher_creates_empty_session_midi_clip():
    context = FakeLiveContext()
    dispatcher = BridgeDispatcher(context)
    payload = make_payload()

    response = dispatcher.dispatch(
        {
            "request_id": "create-1",
            "command": "create_midi_clip",
            "params": {"track_index": 0, "scene_index": 0, "payload": payload},
        }
    )

    slot = context.song().tracks[0].clip_slots[0]
    assert slot.created_length == 16.0
    assert slot.clip.added
    assert isinstance(slot.clip.added, tuple)
    assert response["result"] == {
        "inserted": True,
        "track_index": 0,
        "scene_index": 0,
        "clip_length_beats": 16.0,
        "note_count": len(payload["notes"]),
        "schema_version": 1,
    }


@pytest.mark.parametrize(
    ("track", "code"),
    [
        (FakeTrack(has_clip=True), "TARGET_CLIP_SLOT_NOT_EMPTY"),
        (FakeTrack(has_midi_input=False), "TRACK_NOT_MIDI"),
    ],
)
def test_dispatcher_refuses_unsafe_or_incompatible_target(track, code):
    dispatcher = BridgeDispatcher(FakeLiveContext(track))

    with pytest.raises(BridgeCommandError) as caught:
        dispatcher.dispatch(
            {
                "request_id": "create-2",
                "command": "create_midi_clip",
                "params": {
                    "track_index": 0,
                    "scene_index": 0,
                    "payload": make_payload(),
                },
            }
        )

    assert caught.value.code == code


@pytest.mark.parametrize(
    ("track_index", "scene_index", "code"),
    [(1, 0, "TRACK_NOT_FOUND"), (0, 1, "SCENE_NOT_FOUND")],
)
def test_dispatcher_rejects_missing_track_or_scene(track_index, scene_index, code):
    dispatcher = BridgeDispatcher(FakeLiveContext())

    with pytest.raises(BridgeCommandError) as caught:
        dispatcher.dispatch(
            {
                "request_id": "create-3",
                "command": "create_midi_clip",
                "params": {
                    "track_index": track_index,
                    "scene_index": scene_index,
                    "payload": make_payload(),
                },
            }
        )

    assert caught.value.code == code


def test_remote_script_sources_compile_without_live_installed():
    root = Path(__file__).parents[1] / "ableton_remote_script" / "MidiGeneratorBridge"

    for path in root.glob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_remote_script_does_not_depend_on_project_package():
    root = Path(__file__).parents[1] / "ableton_remote_script" / "MidiGeneratorBridge"

    assert all(
        "midi_generator" not in path.read_text(encoding="utf-8")
        for path in root.glob("*.py")
    )


def test_remote_control_surface_uses_live_midi_note_specifications():
    source = (
        Path(__file__).parents[1]
        / "ableton_remote_script"
        / "MidiGeneratorBridge"
        / "control_surface.py"
    ).read_text(encoding="utf-8")

    assert "from Live.Clip import MidiNoteSpecification" in source
    assert "note_factory=MidiNoteSpecification" in source


def test_external_adapter_does_not_generate_music():
    root = Path(__file__).parents[1] / "src" / "midi_generator" / "ableton"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    assert "generate_plan" not in source
    assert "MelodyRequest" not in source
    assert "random" not in source


def test_remote_socket_server_queues_command_for_main_thread():
    commands = queue.Queue()
    server = BridgeSocketServer(commands, "127.0.0.1", 0)
    server.start()
    result = []

    def call_ping():
        result.append(AbletonClient(port=server.port).ping())

    client_thread = threading.Thread(target=call_ping)
    client_thread.start()
    pending = commands.get(timeout=2)
    assert pending.request["command"] == "ping"
    pending.respond(
        {
            "request_id": pending.request["request_id"],
            "ok": True,
            "result": {"application": "Ableton Live"},
        }
    )
    client_thread.join(timeout=2)
    server.stop()

    assert not client_thread.is_alive()
    assert result == [{"application": "Ableton Live"}]


def test_install_helper_copies_only_bundled_remote_script(tmp_path):
    destination = install_remote_script(tmp_path)

    assert destination == tmp_path / "MidiGeneratorBridge"
    assert (destination / "__init__.py").exists()
    assert (destination / "bridge_core.py").exists()
    assert not (destination / "__pycache__").exists()
