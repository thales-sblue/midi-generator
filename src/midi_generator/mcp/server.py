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
from midi_generator.generation.drums import (
    DEFAULT_KICK_PLACEMENT,
    DEFAULT_KICK_VELOCITY,
    DEFAULT_SNARE_VELOCITY,
)
from midi_generator.integration import (
    ClipProfilePayload,
    IntegrationPayload,
    ableton_snapshot_to_clip,
    clip_profile_to_payload,
    composition_to_payload,
    validate_payload_v1,
)
from midi_generator.mcp import audio_tools
from midi_generator.mcp.ableton_transform import (
    BassLineClipResult,
    ChordBedClipResult,
    ContextualVariationResult,
    KickClipResult,
    SnareClipResult,
    TransformedClipResult,
    create_bass_line_midi_clip_copy,
    create_chord_bed_midi_clip_copy,
    create_contextual_midi_clip_copy,
    create_kick_midi_clip_copy,
    create_snare_midi_clip_copy,
    transform_midi_clip_copy,
)

mcp = MCPServer(
    "midi-generator",
    description="Deterministic melody generation exposed as Integration Payload v1.",
    version="1.11.0",
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
def analyze_audio_file(
    path: str,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
) -> audio_tools.AudioAnalysisResult:
    """Analyse a local recording: tempo, beat times, metre, key and chords per bar.

    Every estimate carries a confidence; treat low values as guesses to confirm
    with the user. ``beats_per_bar`` fixes the metre instead of choosing 4 vs 3.
    ``tempo_hint`` (approximate BPM) fixes a tempo read at half or double speed.
    """
    try:
        return audio_tools.analyze_audio_file(
            path, beats_per_bar=beats_per_bar, tempo_hint=tempo_hint
        )
    except (FileNotFoundError, ValueError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def generate_accompaniment_from_audio(
    path: str,
    style: str = "basic",
    seed: int = 0,
    sustain_bass: bool = True,
    follow_recording: bool = True,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
) -> audio_tools.AudioAccompanimentResult:
    """Analyse a recording and write a bass and a drum MIDI file that follow it.

    The bass plays the root of every detected chord inside the detected key;
    the drums (``style="basic"``) put the kick on beats 1 and 3, the snare on 2
    and 4 and a closed hi-hat on eighths. Files go to
    ``output/accompaniment/<name>.bass.mid`` / ``.drums.mid`` with the analysis
    as ``.analysis.json``. With ``follow_recording`` (default) the MIDI carries
    the recording's own beat timing and lead-in, so it plays in sync when
    started together with the audio; otherwise it starts at bar 1 at the
    rounded tempo. Nothing is written to Ableton.
    """
    try:
        return audio_tools.create_accompaniment_files(
            path,
            style=style,
            seed=seed,
            sustain_bass=sustain_bass,
            follow_recording=follow_recording,
            beats_per_bar=beats_per_bar,
            tempo_hint=tempo_hint,
        )
    except (FileNotFoundError, ValueError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def insert_audio_accompaniment_into_ableton(
    path: str,
    bass_track_index: int,
    drums_track_index: int,
    scene_index: int,
    style: str = "basic",
    seed: int = 0,
    sustain_bass: bool = True,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
) -> audio_tools.AccompanimentClipsResult:
    """Analyse a recording and create a bass clip and a drum clip in Ableton.

    Both clips are new Session View clips in empty slots of the same scene, on
    two different MIDI tracks; an occupied slot, a missing or non-MIDI track
    and a recording not read as 4/4 are refused before anything is written,
    and no existing clip is ever changed. The clips start on bar 1 in beats:
    the result says which tempo to set and where the recording's first
    downbeat is, so the audio can be lined up with them.
    """
    try:
        return audio_tools.insert_accompaniment_clips(
            path,
            AbletonClient(),
            bass_track_index=bass_track_index,
            drums_track_index=drums_track_index,
            scene_index=scene_index,
            style=style,
            seed=seed,
            sustain_bass=sustain_bass,
            beats_per_bar=beats_per_bar,
            tempo_hint=tempo_hint,
        )
    except (FileNotFoundError, ValueError, AbletonError) as error:
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
    placement: str = DEFAULT_KICK_PLACEMENT,
) -> KickClipResult:
    """Generate a kick pattern for a source clip into a protected copy.

    Reads the source MIDI clip, builds a length-matched request and delegates
    every musical decision to ``generate_kick_plan``. ``placement`` picks where
    the kicks land: ``"per_onset"`` (default) doubles each distinct sounding
    onset of the reference, ``"downbeat_only"`` plays the first beat of every
    bar, ``"four_on_floor"`` every quarter note and ``"odd_beats"`` beats 1
    and 3 of a 4/4 bar; the generator validates it.
    The source clip is never overwritten: the kicks land only in the empty
    ``target`` slot after a fingerprint-protected duplication. A kick is
    unpitched, so ``root_note`` and ``scale`` are carried only for provenance
    continuity and are not inferred from the clip.
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
            placement=placement,
        )
    except (ValueError, AbletonError) as error:
        raise ToolError(str(error)) from error


@mcp.tool()
def create_snare_from_ableton_clip(
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
    velocity: int = DEFAULT_SNARE_VELOCITY,
) -> SnareClipResult:
    """Generate a snare backbeat for a source clip into a protected copy.

    Reads the source MIDI clip, builds a length-matched request and delegates
    every musical decision to ``generate_snare_plan``: a snare on the 2nd,
    4th, ... beat of every bar, a fixed grid derived from the clip's length
    and metre, not from its onsets. The source clip is never overwritten: the
    snares land only in the empty ``target`` slot after a fingerprint-protected
    duplication. A snare is unpitched, so ``root_note`` and ``scale`` are
    carried only for provenance continuity and are not inferred from the clip.
    """
    try:
        return create_snare_midi_clip_copy(
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
