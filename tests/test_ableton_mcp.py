import asyncio

from mcp import Client

from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import composition_to_payload
from midi_generator.mcp.server import (
    generate_and_insert_melody,
    generate_melody,
    get_ableton_session,
    mcp,
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
