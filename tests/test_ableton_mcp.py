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
    transform_ableton_midi_clip,
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

    def duplicate_midi_clip(
        self,
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        expected_source_fingerprint=None,
    ):
        self.duplicated = (
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            expected_source_fingerprint,
        )
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
    assert fake.duplicated == (0, 1, 0, 2, None)
    assert duplicated["duplicated"] is True


def test_duplicate_tool_propagates_optional_source_fingerprint(monkeypatch):
    fake = FakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = duplicate_ableton_midi_clip(
        0, 0, 0, 1, expected_source_fingerprint="source-fingerprint"
    )

    assert result["duplicated"] is True
    assert fake.duplicated == (0, 0, 0, 1, "source-fingerprint")


def test_mcp_client_calls_read_clip_tool(monkeypatch):
    fake = FakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    async def call_tool():
        async with Client(mcp) as client:
            return await client.call_tool("get_ableton_midi_clip", {"track_index": 0, "scene_index": 0})

    result = asyncio.run(call_tool())
    assert result.is_error is False
    assert result.structured_content["clip_fingerprint"] == "abc"


class TransformingFakeAbletonClient(FakeAbletonClient):
    def __init__(self):
        super().__init__()
        self.reads = []

    def get_midi_clip(self, track_index, scene_index):
        self.reads.append((track_index, scene_index))
        fingerprint = "source" if (track_index, scene_index) == (0, 0) else "copy"
        return {
            "track_index": track_index,
            "scene_index": scene_index,
            "clip_length_beats": 4.0,
            "notes": [{"pitch": 60, "start_time": 0.5, "duration": 0.5, "velocity": 90, "mute": False}],
            "clip_fingerprint": fingerprint,
        }

    def replace_midi_clip_notes(self, track_index, scene_index, expected_fingerprint, notes):
        self.replaced = (track_index, scene_index, expected_fingerprint, notes)
        return {"replaced": True, "clip_length_beats": 4.0, "note_count": len(notes), "clip_fingerprint": "result"}


def test_transform_tool_returns_structured_result_and_only_edits_copy(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(0, 0, 0, 1, "transpose", semitones=12)

    assert fake.reads == [(0, 0), (0, 1)]
    assert fake.duplicated == (0, 0, 0, 1, "source")
    assert fake.replaced[:3] == (0, 1, "copy")
    assert fake.replaced[3][0]["pitch"] == 72
    assert result["source_clip_fingerprint"] == "source"
    assert result["target_clip_fingerprint"] == "result"


def test_transform_tool_exposes_retrograde_without_extra_parameters(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(0, 0, 0, 1, "retrograde")

    assert fake.replaced[3][0]["start_time"] == 3.0
    assert result["transform"] == "retrograde"


def test_transform_tool_exposes_melodic_inversion(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    async def call_tool():
        async with Client(mcp) as client:
            return await client.call_tool(
                "transform_ableton_midi_clip",
                {
                    "source_track_index": 0,
                    "source_scene_index": 0,
                    "target_track_index": 0,
                    "target_scene_index": 1,
                    "transform": "invert",
                    "axis_pitch": 64,
                },
            )

    result = asyncio.run(call_tool())

    assert fake.replaced[3][0]["pitch"] == 68
    assert result.is_error is False
    assert result.structured_content["transform"] == "invert"


def test_transform_tool_exposes_legato_without_extra_parameters(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(0, 0, 0, 1, "legato")

    assert fake.replaced[3][0]["duration"] == 3.5
    assert result["transform"] == "legato"


def test_transform_tool_exposes_staccato_with_max_duration(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(
        0, 0, 0, 1, "staccato", max_duration=0.25
    )

    assert fake.replaced[3][0]["duration"] == 0.25
    assert result["transform"] == "staccato"


def test_transform_tool_exposes_scale_constraint(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(
        0, 0, 0, 1, "constrain_to_scale", root_note="C", scale="major"
    )

    assert fake.replaced[3][0]["pitch"] == 60
    assert result["transform"] == "constrain_to_scale"


def test_transform_tool_exposes_diatonic_transposition(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(
        0,
        0,
        0,
        1,
        "transpose_diatonic",
        steps=2,
        root_note="C",
        scale="major",
    )

    assert fake.replaced[3][0]["pitch"] == 64
    assert result["transform"] == "transpose_diatonic"


def test_transform_tool_exposes_non_destructive_diatonic_harmony(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(
        0,
        0,
        0,
        1,
        "harmonize_diatonic",
        steps=2,
        root_note="C",
        scale="major",
    )

    assert [note["pitch"] for note in fake.replaced[3]] == [60, 64]
    assert fake.duplicated == (0, 0, 0, 1, "source")
    assert result["note_count"] == 2
    assert result["transform"] == "harmonize_diatonic"


def test_transform_tool_exposes_non_destructive_velocity_ramp(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    result = transform_ableton_midi_clip(
        0,
        0,
        0,
        1,
        "velocity_ramp",
        start_velocity=40,
        end_velocity=100,
    )

    assert fake.replaced[3][0]["velocity"] == 40
    assert fake.duplicated == (0, 0, 0, 1, "source")
    assert result["transform"] == "velocity_ramp"


def test_real_mcp_client_discovers_and_calls_transform_tool(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    async def call_tool():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                "transform_ableton_midi_clip",
                {"source_track_index": 0, "source_scene_index": 0, "target_track_index": 0, "target_scene_index": 1, "transform": "quantize", "grid": "1/16"},
            )
            return tools, result

    tools, result = asyncio.run(call_tool())

    assert "transform_ableton_midi_clip" in {tool.name for tool in tools.tools}
    tool = next(tool for tool in tools.tools if tool.name == "transform_ableton_midi_clip")
    assert set(tool.output_schema["required"]) >= {
        "transformed",
        "transform",
        "source_clip_fingerprint",
        "target_clip_fingerprint",
    }
    assert result.is_error is False
    assert result.structured_content["transformed"] is True
    assert result.structured_content["target_clip_fingerprint"] == "result"


def test_transform_tool_validates_parameters_before_ableton_read(monkeypatch):
    fake = TransformingFakeAbletonClient()
    monkeypatch.setattr("midi_generator.mcp.server.AbletonClient", lambda: fake)

    async def call_tool():
        async with Client(mcp) as client:
            return await client.call_tool(
                "transform_ableton_midi_clip",
                {"source_track_index": 0, "source_scene_index": 0, "target_track_index": 0, "target_scene_index": 1, "transform": "humanize", "seed": 42},
            )

    result = asyncio.run(call_tool())

    assert result.is_error is True
    assert "humanize requires" in result.content[0].text
    assert fake.reads == []
