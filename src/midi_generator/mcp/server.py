"""MCP server exposing the existing deterministic composition engine."""

from typing import Any, TypedDict

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from midi_generator.ableton import AbletonClient, AbletonError
from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import (
    IntegrationPayload,
    composition_to_payload,
    validate_payload_v1,
)
from midi_generator.mcp.ableton_transform import (
    TransformedClipResult,
    transform_midi_clip_copy,
)

mcp = MCPServer(
    "midi-generator",
    description="Deterministic melody generation exposed as Integration Payload v1.",
    version="1.2.0",
)


class InsertedClipResult(TypedDict):
    inserted: bool
    track_index: int
    scene_index: int
    clip_length_beats: float
    note_count: int
    schema_version: int


@mcp.tool()
def generate_melody(
    bpm: int,
    root_note: str,
    scale: str,
    bars: int,
    seed: int,
) -> IntegrationPayload:
    """Generate a deterministic melody and return Integration Payload v1."""
    try:
        return _generate_payload(bpm, root_note, scale, bars, seed)
    except ValueError as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def get_ableton_session() -> dict[str, Any]:
    """Get the minimal Ableton Session state needed to choose a clip slot."""
    try:
        return AbletonClient().get_session_state()
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def get_ableton_midi_clip(track_index: int, scene_index: int) -> dict[str, Any]:
    """Read the editable MIDI note content and fingerprint of an Ableton clip."""
    try:
        return AbletonClient().get_midi_clip(track_index, scene_index)
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def replace_ableton_midi_clip_notes(
    track_index: int,
    scene_index: int,
    expected_fingerprint: str,
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace MIDI notes only if the Ableton clip fingerprint still matches."""
    try:
        return AbletonClient().replace_midi_clip_notes(
            track_index, scene_index, expected_fingerprint, notes
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def duplicate_ableton_midi_clip(
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    expected_source_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Duplicate an Ableton MIDI clip, optionally requiring its fingerprint."""
    try:
        client = AbletonClient()
        indices = (
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
        )
        if expected_source_fingerprint is None:
            return client.duplicate_midi_clip(*indices)
        return client.duplicate_midi_clip(
            *indices,
            expected_source_fingerprint=expected_source_fingerprint,
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def transform_ableton_midi_clip(
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    transform: str,
    semitones: int | None = None,
    grid: str | None = None,
    seed: int | None = None,
    max_timing_shift: float | None = None,
    max_velocity_delta: int | None = None,
) -> TransformedClipResult:
    """Apply a deterministic transform to a duplicate in an empty clip slot."""
    try:
        return transform_midi_clip_copy(
            AbletonClient(),
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            transform,
            semitones,
            grid,
            seed,
            max_timing_shift,
            max_velocity_delta,
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def generate_and_insert_melody(
    bpm: int,
    root_note: str,
    scale: str,
    bars: int,
    seed: int,
    track_index: int,
    scene_index: int,
) -> InsertedClipResult:
    """Generate a melody and insert it into an empty Ableton Session clip slot."""
    try:
        payload = _generate_payload(bpm, root_note, scale, bars, seed)
        validate_payload_v1(payload)
        result = AbletonClient().create_midi_clip(track_index, scene_index, payload)
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error
    return InsertedClipResult(**result)


def _generate_payload(
    bpm: int,
    root_note: str,
    scale: str,
    bars: int,
    seed: int,
) -> IntegrationPayload:
    request = MelodyRequest(
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        bars=bars,
        seed=seed,
    )
    plan = generate_plan(request)
    return composition_to_payload(plan)


def main() -> None:
    """Run the local MCP server over the default stdio transport."""
    mcp.run(transport="stdio")
