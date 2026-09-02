"""MCP server exposing the existing deterministic composition engine."""

from typing import Any, TypedDict

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from midi_generator.ableton import AbletonClient, AbletonError
from midi_generator.analysis import analyze_clip
from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_contextual_plan, generate_plan
from midi_generator.generation.bass_line import DEFAULT_BASS_VELOCITY
from midi_generator.generation.chords import DEFAULT_CHORD_VELOCITY
from midi_generator.generation.drums import DEFAULT_KICK_VELOCITY
from midi_generator.integration import (
    ClipProfilePayload,
    IntegrationPayload,
    ableton_snapshot_to_clip,
    clip_profile_to_payload,
    composition_to_payload,
    validate_payload_v1,
)
from midi_generator.mcp.ableton_transform import (
    BassLineClipResult,
    ChordBedClipResult,
    ContextualVariationResult,
    KickClipResult,
    TransformedClipResult,
    create_bass_line_midi_clip_copy,
    create_chord_bed_midi_clip_copy,
    create_contextual_midi_clip_copy,
    create_kick_midi_clip_copy,
    transform_midi_clip_copy,
)

mcp = MCPServer(
    "midi-generator",
    description="Deterministic melody generation exposed as Integration Payload v1.",
    version="1.8.0",
)


class InsertedClipResult(TypedDict):
    inserted: bool
    track_index: int
    scene_index: int
    clip_length_beats: float
    note_count: int
    schema_version: int


class AnalyzedClipResult(TypedDict):
    analyzed: bool
    track_index: int
    scene_index: int
    clip_fingerprint: str
    profile: ClipProfilePayload


class ContextualMelodyResult(TypedDict):
    source_track_index: int
    source_scene_index: int
    source_clip_fingerprint: str
    composition: IntegrationPayload


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
def analyze_ableton_midi_clip(
    track_index: int, scene_index: int
) -> AnalyzedClipResult:
    """Read an Ableton MIDI clip and return its objective musical profile."""
    try:
        snapshot = AbletonClient().get_midi_clip(track_index, scene_index)
        fingerprint = snapshot.get("clip_fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError(
                "Ableton clip snapshot must include a clip_fingerprint."
            )
        profile = analyze_clip(ableton_snapshot_to_clip(snapshot))
        return AnalyzedClipResult(
            analyzed=True,
            track_index=track_index,
            scene_index=scene_index,
            clip_fingerprint=fingerprint,
            profile=clip_profile_to_payload(profile),
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def generate_contextual_melody_from_ableton_clip(
    source_track_index: int,
    source_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    bars: int,
    seed: int,
) -> ContextualMelodyResult:
    """Generate a melody shaped by a source clip without changing Ableton."""
    try:
        snapshot = AbletonClient().get_midi_clip(
            source_track_index, source_scene_index
        )
        fingerprint = snapshot.get("clip_fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError(
                "Ableton clip snapshot must include a clip_fingerprint."
            )
        request = MelodyRequest(bpm, root_note, scale, bars, seed)
        plan = generate_contextual_plan(
            request, ableton_snapshot_to_clip(snapshot)
        )
        return ContextualMelodyResult(
            source_track_index=source_track_index,
            source_scene_index=source_scene_index,
            source_clip_fingerprint=fingerprint,
            composition=composition_to_payload(plan),
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def create_contextual_variation_from_ableton_clip(
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
) -> ContextualVariationResult:
    """Generate a contextual melody into a protected duplicate of the source."""
    try:
        return create_contextual_midi_clip_copy(
            AbletonClient(),
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            bpm,
            root_note,
            scale,
            seed,
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def create_bass_line_from_ableton_clip(
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
    segment_beats: int = 1,
    velocity: int = DEFAULT_BASS_VELOCITY,
    sustain: bool = False,
    octave: int | None = None,
) -> BassLineClipResult:
    """Generate a diatonic bass line for a source clip into a protected copy.

    Reads the source MIDI clip, builds a length-matched request and delegates
    every musical decision to ``generate_bass_line_plan``. The source clip is
    never overwritten: the notes land only in the empty ``target`` slot after a
    fingerprint-protected duplication. ``root_note`` and ``scale`` are an
    explicit choice of the caller.
    """
    try:
        return create_bass_line_midi_clip_copy(
            AbletonClient(),
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            bpm,
            root_note,
            scale,
            seed,
            segment_beats=segment_beats,
            velocity=velocity,
            sustain=sustain,
            octave=octave,
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def create_chord_bed_from_ableton_clip(
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
    segment_beats: int = 1,
    velocity: int = DEFAULT_CHORD_VELOCITY,
    sustain: bool = False,
    octave: int | None = None,
    chord_size: int = 3,
) -> ChordBedClipResult:
    """Generate a diatonic chord bed for a source clip into a protected copy.

    Reads the source MIDI clip, builds a length-matched request and delegates
    every musical decision to ``generate_chord_bed_plan``. The source clip is
    never overwritten: the chords land only in the empty ``target`` slot after a
    fingerprint-protected duplication. ``root_note`` and ``scale`` are an
    explicit choice of the caller.
    """
    try:
        return create_chord_bed_midi_clip_copy(
            AbletonClient(),
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            bpm,
            root_note,
            scale,
            seed,
            segment_beats=segment_beats,
            velocity=velocity,
            sustain=sustain,
            octave=octave,
            chord_size=chord_size,
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def create_kick_from_ableton_clip(
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
    velocity: int = DEFAULT_KICK_VELOCITY,
) -> KickClipResult:
    """Generate a kick pattern for a source clip into a protected copy.

    Reads the source MIDI clip, builds a length-matched request and delegates
    every musical decision to ``generate_kick_plan`` — one kick on each distinct
    sounding onset of the reference. The source clip is never overwritten: the
    kicks land only in the empty ``target`` slot after a fingerprint-protected
    duplication. A kick is unpitched, so ``root_note`` and ``scale`` are carried
    only for provenance continuity and are not inferred from the clip.
    """
    try:
        return create_kick_midi_clip_copy(
            AbletonClient(),
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            bpm,
            root_note,
            scale,
            seed,
            velocity=velocity,
        )
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
    axis_pitch: int | None = None,
    max_duration: float | None = None,
    root_note: str | None = None,
    scale: str | None = None,
    steps: int | None = None,
    start_velocity: int | None = None,
    end_velocity: int | None = None,
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
            semitones=semitones,
            grid=grid,
            seed=seed,
            max_timing_shift=max_timing_shift,
            max_velocity_delta=max_velocity_delta,
            axis_pitch=axis_pitch,
            max_duration=max_duration,
            root_note=root_note,
            scale=scale,
            steps=steps,
            start_velocity=start_velocity,
            end_velocity=end_velocity,
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
