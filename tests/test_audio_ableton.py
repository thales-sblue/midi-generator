"""Audio accompaniment inserted as new Session View clips through the bridge.

The analysis is stubbed with a hand-built MusicAnalysis (the audio path has
its own tests); what is checked here is the orchestration: nothing touches
Live before analysis and generation succeed, occupied or unsuitable targets
are refused before any write, and the created clips hold exactly the planned
notes (verified against the real BridgeDispatcher on an in-memory Live).
"""

import asyncio

import pytest
from mcp import Client

from midi_generator.ableton import AbletonCommandError, AbletonError
from midi_generator.generation import (
    generate_bass_from_analysis,
    generate_drums_from_analysis,
)
from midi_generator.integration import composition_to_payload
from midi_generator.mcp import audio_tools
from midi_generator.mcp.server import mcp
from test_accompaniment import make_analysis
from test_ableton_verification import (
    DispatcherClient,
    FakeClip,
    FakeClipSlot,
    FakeLiveContext,
)

ANALYSIS = make_analysis()


@pytest.fixture(autouse=True)
def stub_analysis(monkeypatch):
    calls = []

    def fake_analyze(path, beats_per_bar, tempo_hint):
        calls.append((path, beats_per_bar, tempo_hint))
        return ANALYSIS

    monkeypatch.setattr(audio_tools, "_analyze", fake_analyze)
    return calls


class MultiTrack:
    def __init__(self, name, slots, midi=True):
        self.name = name
        self.has_midi_input = midi
        self.clip_slots = slots


def live_with(*tracks):
    context = FakeLiveContext(tracks[0])
    context._song.tracks = list(tracks)
    return context


class BridgeClient(DispatcherClient):
    """The real dispatcher, plus the two commands this flow uses."""

    def get_session_state(self):
        return self._dispatch("get_session_state", {})

    def create_midi_clip(self, track_index, scene_index, payload):
        return self._dispatch(
            "create_midi_clip",
            {"track_index": track_index, "scene_index": scene_index, "payload": payload},
        )


def insert(client, **overrides):
    arguments = dict(
        bass_track_index=0,
        drums_track_index=1,
        scene_index=0,
        style="basic",
        seed=0,
        sustain_bass=True,
    )
    arguments.update(overrides)
    return audio_tools.insert_accompaniment_clips("take.wav", client, **arguments)


def two_empty_tracks():
    return live_with(
        MultiTrack("Bass", [FakeClipSlot(), FakeClipSlot()]),
        MultiTrack("Drums", [FakeClipSlot(), FakeClipSlot()]),
    )


def test_creates_bass_and_drum_clips_with_the_planned_notes():
    context = two_empty_tracks()

    result = insert(BridgeClient(context), scene_index=1)

    bass_clip = context._song.tracks[0].clip_slots[1].clip
    drums_clip = context._song.tracks[1].clip_slots[1].clip
    expected_bass = composition_to_payload(generate_bass_from_analysis(ANALYSIS))
    expected_drums = composition_to_payload(generate_drums_from_analysis(ANALYSIS))

    def as_ticks(clip):
        return sorted(
            (note.pitch, round(note.start_time * 480), round(note.duration * 480))
            for note in clip.notes
        )

    def planned(payload):
        return sorted((n["pitch"], n["start"], n["duration"]) for n in payload["notes"])

    assert as_ticks(bass_clip) == planned(expected_bass)
    assert as_ticks(drums_clip) == planned(expected_drums)
    assert bass_clip.length == drums_clip.length == 16.0  # 4 bars of 4/4
    assert result["bass"] == {
        "track_index": 0,
        "scene_index": 1,
        "clip_length_beats": 16.0,
        "note_count": len(expected_bass["notes"]),
    }
    assert result["drums"]["track_index"] == 1
    assert result["bars"] == 4
    assert result["rounded_bpm"] == 92
    assert result["tempo_bpm"] == pytest.approx(92.0, abs=0.01)
    assert (result["root_note"], result["scale"]) == ("A", "minor")
    assert result["first_downbeat_seconds"] == pytest.approx(0.4)
    assert "0.4 s" in result["alignment"]
    # Untouched: the other scene stays empty.
    assert not context._song.tracks[0].clip_slots[0].has_clip


def test_forwards_analysis_options(stub_analysis):
    insert(BridgeClient(two_empty_tracks()), beats_per_bar=4, tempo_hint=90.0)
    assert stub_analysis == [("take.wav", 4, 90.0)]


class RecordingClient:
    """Answers the preflight from a table and records every call."""

    def __init__(self, slots=None, tracks=None, fail_create_on=None):
        self.calls = []
        self.slots = slots or {}
        self.tracks = tracks or [
            {"index": 0, "name": "Bass", "can_hold_midi": True},
            {"index": 1, "name": "Drums", "can_hold_midi": True},
        ]
        self.fail_create_on = fail_create_on

    def get_session_state(self):
        self.calls.append("get_session_state")
        return {"tracks": self.tracks, "scenes": [{"index": 0, "name": "1"}]}

    def get_midi_clip(self, track_index, scene_index):
        self.calls.append(("get_midi_clip", track_index))
        state = self.slots.get(track_index, "empty")
        if state == "empty":
            raise AbletonCommandError("CLIP_NOT_FOUND", "Clip slot is empty.")
        if state == "audio":
            raise AbletonCommandError("CLIP_NOT_MIDI", "Clip is not a MIDI clip.")
        if state == "unavailable":
            raise AbletonError("bridge unavailable")
        return {"notes": [], "clip_fingerprint": "abc"}

    def create_midi_clip(self, track_index, scene_index, payload):
        self.calls.append(("create_midi_clip", track_index))
        if track_index == self.fail_create_on:
            raise AbletonCommandError("TARGET_CLIP_SLOT_NOT_EMPTY", "occupied")
        return {"clip_length_beats": 16.0, "note_count": len(payload["notes"])}


def creates(client):
    return [call for call in client.calls if call[0] == "create_midi_clip"]


def test_refuses_the_same_track_for_both_parts_before_analysing(stub_analysis):
    client = RecordingClient()
    with pytest.raises(ValueError, match="two different tracks"):
        insert(client, drums_track_index=0)
    assert client.calls == []
    assert stub_analysis == []


def test_refuses_a_recording_not_read_as_four_four(monkeypatch):
    monkeypatch.setattr(
        audio_tools, "_analyze", lambda *args: make_analysis(per_bar=3)
    )
    client = RecordingClient()
    with pytest.raises(ValueError, match="3/4"):
        insert(client)
    assert client.calls == []


def test_generation_errors_happen_before_live_is_contacted():
    client = RecordingClient()
    with pytest.raises(ValueError, match="style"):
        insert(client, style="grunge")
    assert client.calls == []


@pytest.mark.parametrize(
    ("slots", "message"),
    [({1: "occupied"}, "already holds a clip"), ({0: "audio"}, "audio clip")],
)
def test_refuses_occupied_slots_before_creating_anything(slots, message):
    client = RecordingClient(slots=slots)
    with pytest.raises(ValueError, match=message):
        insert(client)
    assert creates(client) == []


@pytest.mark.parametrize(
    ("overrides", "tracks", "message"),
    [
        ({"drums_track_index": 5}, None, "Track 5 does not exist"),
        ({"scene_index": 3}, None, "Scene 3 does not exist"),
        (
            {},
            [
                {"index": 0, "name": "Bass", "can_hold_midi": True},
                {"index": 1, "name": "Audio", "can_hold_midi": False},
            ],
            "cannot hold MIDI",
        ),
    ],
)
def test_refuses_missing_or_unsuitable_targets(overrides, tracks, message):
    client = RecordingClient(tracks=tracks)
    with pytest.raises(ValueError, match=message):
        insert(client, **overrides)
    assert creates(client) == []


def test_bridge_errors_during_preflight_propagate_untouched():
    client = RecordingClient(slots={0: "unavailable"})
    with pytest.raises(AbletonError, match="bridge unavailable"):
        insert(client)
    assert creates(client) == []


def test_a_drum_failure_after_the_bass_clip_is_reported_as_partial():
    client = RecordingClient(fail_create_on=1)
    with pytest.raises(AbletonError, match="bass clip was created at track 0"):
        insert(client)
    assert creates(client) == [("create_midi_clip", 0), ("create_midi_clip", 1)]


def test_a_bass_failure_is_reported_as_is():
    client = RecordingClient(fail_create_on=0)
    with pytest.raises(AbletonCommandError, match="TARGET_CLIP_SLOT_NOT_EMPTY"):
        insert(client)
    assert creates(client) == [("create_midi_clip", 0)]


def test_the_real_bridge_still_refuses_an_occupied_slot():
    occupied = FakeClipSlot(has_clip=True)
    context = live_with(
        MultiTrack("Bass", [FakeClipSlot()]), MultiTrack("Drums", [occupied])
    )
    with pytest.raises(ValueError, match="already holds a clip"):
        insert(BridgeClient(context))
    assert not context._song.tracks[0].clip_slots[0].has_clip
    assert isinstance(occupied.clip, FakeClip) and occupied.clip.notes == []


def test_mcp_tool_is_registered_and_maps_errors(monkeypatch):
    monkeypatch.setattr(
        "midi_generator.mcp.server.AbletonClient", lambda: RecordingClient(slots={1: "occupied"})
    )

    async def run():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                "insert_audio_accompaniment_into_ableton",
                {
                    "path": "take.wav",
                    "bass_track_index": 0,
                    "drums_track_index": 1,
                    "scene_index": 0,
                },
            )
            return {tool.name for tool in tools.tools}, result

    names, result = asyncio.run(run())
    assert "insert_audio_accompaniment_into_ableton" in names
    assert result.is_error is True
    assert "already holds a clip" in result.content[0].text

