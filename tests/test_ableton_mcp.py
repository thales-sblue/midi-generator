import asyncio

from mcp import Client

from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import composition_to_payload
from midi_generator.mcp.server import (
    duplicate_ableton_midi_clip,
    generate_and_insert_melody,
    generate_melody,
    get_ableton_midi_clip,
    get_ableton_session,
    mcp,
    replace_ableton_midi_clip_notes,
)


VALID_ARGUMENTS = {
    "bpm": 120,
    "root_note": "C",
    "scale": "minor",
    "bars": 4,
    "seed": 42,
}


class FakeAbletonClient:
    def __init__(self):
        self.created = None

    def get_session_state(self):
        return {
            "tracks": [{"index": 0, "name": "MIDI", "can_hold_midi": True}],
            "scenes": [{"index": 0, "name": "Scene 1"}],
        }

    def create_midi_clip(self, track_index, scene_index, payload):
        self.created = (track_index, scene_index, payload)
        return {
            "inserted": True,
            "track_index": track_index,
            "scene_index": scene_index,
            "clip_length_beats": 16.0,
            "note_count": len(payload["notes"]),
            "schema_version": payload["schema_version"],
        }

    def get_midi_clip(self, track_index, scene_index):
        return {"track_index": track_index, "scene_index": scene_index, "notes": [], "clip_fingerprint": "abc"}

    def replace_midi_clip_notes(self, track_index, scene_index, expected_fingerprint, notes):
        self.replaced = (track_index, scene_index, expected_fingerprint, notes)
        return {"replaced": True, "clip_fingerprint": "def"}

    def duplicate_midi_clip(self, source_track_index, source_scene_index, target_track_index, target_scene_index):
        self.duplicated = (source_track_index, source_scene_index, target_track_index, target_scene_index)
        return {"duplicated": True, "clip_fingerprint": "abc"}


def test_get_ableton_session_uses_external_client(monkeypatch):
    fake = FakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = get_ableton_session()

    assert result["tracks"][0]["can_hold_midi"] is True


def test_generate_and_insert_reuses_engine_and_exact_serializer_payload(monkeypatch):
    fake = FakeAbletonClient()
    captured_requests = []

    def capture_generate_plan(request):
        captured_requests.append(request)
        return generate_plan(request)

    monkeypatch.setattr("midi_generator.mcp.server.generate_plan", capture_generate_plan)
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = generate_and_insert_melody(
        **VALID_ARGUMENTS, track_index=0, scene_index=0
    )

    expected_request = MelodyRequest(**VALID_ARGUMENTS)
    expected_payload = composition_to_payload(generate_plan(expected_request))
    assert captured_requests == [expected_request]
    assert fake.created == (0, 0, expected_payload)
    assert result["inserted"] is True
    assert result["schema_version"] == 1


def test_generate_melody_still_works_without_ableton(monkeypatch):
    def fail_if_constructed():
        raise AssertionError("AbletonClient must not be constructed")

    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", fail_if_constructed)

    payload = generate_melody(**VALID_ARGUMENTS)

    assert payload == composition_to_payload(
        generate_plan(MelodyRequest(**VALID_ARGUMENTS))
    )


def test_mcp_client_calls_generate_and_insert_tool(monkeypatch):
    fake = FakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    async def call_tool():
        async with Client(mcp) as client:
            return await client.call_tool(
                "generate_and_insert_melody",
                VALID_ARGUMENTS | {"track_index": 0, "scene_index": 0},
            )

    result = asyncio.run(call_tool())

    assert result.is_error is False
    assert result.structured_content["inserted"] is True
    assert result.structured_content["schema_version"] == 1


def test_clip_tools_only_delegate_to_ableton_client(monkeypatch):
    fake = FakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)
    notes = [{"pitch": 72, "start_time": 0.0, "duration": 1.0, "velocity": 90, "mute": False}]

    read = get_ableton_midi_clip(0, 1)
    replaced = replace_ableton_midi_clip_notes(0, 1, "abc", notes)
    duplicated = duplicate_ableton_midi_clip(0, 1, 0, 2)

    assert read["clip_fingerprint"] == "abc"
    assert fake.replaced == (0, 1, "abc", notes)
    assert replaced["replaced"] is True
    assert fake.duplicated == (0, 1, 0, 2)
    assert duplicated["duplicated"] is True


def test_mcp_client_calls_read_clip_tool(monkeypatch):
    fake = FakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    async def call_tool():
        async with Client(mcp) as client:
            return await client.call_tool("get_ableton_midi_clip", {"track_index": 0, "scene_index": 0})

    result = asyncio.run(call_tool())
    assert result.is_error is False
    assert result.structured_content["clip_fingerprint"] == "abc"
