"""MCP orchestration for audio analysis and accompaniment.

No musical decision is made here: the analysis comes from
``midi_generator.audio``, the parts from ``generation.accompaniment``, the
files from ``exporters`` and the Live clips from the bridge's existing
``create_midi_clip``. The audio package is imported lazily so the MCP server
starts without loading librosa until an audio tool is called.
"""

from pathlib import Path
from typing import Any, TypedDict

from midi_generator.ableton import AbletonCommandError, AbletonError
from midi_generator.domain import MusicAnalysis, TimeSignature
from midi_generator.exporters import export_accompaniment
from midi_generator.generation import generate_accompaniment
from midi_generator.integration import composition_to_payload, validate_payload_v1

# The bridge only creates 4/4 clips.
_BRIDGE_TIME_SIGNATURE = TimeSignature(4, 4)

# Accompaniment files always land here, relative to the server's working
# directory; callers choose the recording, never the destination.
ACCOMPANIMENT_FOLDER = Path("output") / "accompaniment"


class AudioAnalysisResult(TypedDict):
    summary: str
    analysis: dict[str, Any]


class AudioAccompanimentResult(TypedDict):
    summary: str
    style: str
    seed: int
    bars: int
    bpm: int
    root_note: str
    scale: str
    time_signature: str
    follows_recording: bool
    first_downbeat_seconds: float
    bass_note_count: int
    drum_note_count: int
    bass_midi_path: str
    drums_midi_path: str
    analysis_path: str
    warnings: list[str]


def analyze_audio_file(
    path: str,
    *,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
) -> AudioAnalysisResult:
    analysis = _analyze(path, beats_per_bar, tempo_hint)
    return AudioAnalysisResult(summary=analysis.summary(), analysis=analysis.to_dict())


def create_accompaniment_files(
    path: str,
    *,
    style: str,
    seed: int,
    sustain_bass: bool,
    follow_recording: bool,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
) -> AudioAccompanimentResult:
    analysis = _analyze(path, beats_per_bar, tempo_hint)
    accompaniment = generate_accompaniment(
        analysis, style=style, seed=seed, sustain_bass=sustain_bass
    )
    files = export_accompaniment(
        accompaniment,
        analysis,
        ACCOMPANIMENT_FOLDER,
        Path(path).stem,
        follow_recording=follow_recording,
    )
    request = accompaniment.bass.request
    return AudioAccompanimentResult(
        summary=analysis.summary(),
        style=style,
        seed=seed,
        bars=request.bars,
        bpm=request.bpm,
        root_note=request.root_note,
        scale=request.scale,
        time_signature=str(request.time_signature),
        follows_recording=follow_recording,
        first_downbeat_seconds=round(analysis.grid.first_downbeat_seconds, 4),
        bass_note_count=len(accompaniment.bass.notes),
        drum_note_count=len(accompaniment.drums.notes),
        bass_midi_path=str(files.bass.resolve()),
        drums_midi_path=str(files.drums.resolve()),
        analysis_path=str(files.analysis.resolve()),
        warnings=list(accompaniment.bass.report.warnings),
    )


class InsertedPartResult(TypedDict):
    track_index: int
    scene_index: int
    clip_length_beats: float
    note_count: int


class AccompanimentClipsResult(TypedDict):
    summary: str
    style: str
    seed: int
    bars: int
    tempo_bpm: float
    rounded_bpm: int
    root_note: str
    scale: str
    first_downbeat_seconds: float
    bass: InsertedPartResult
    drums: InsertedPartResult
    warnings: list[str]
    alignment: str


def insert_accompaniment_clips(
    path: str,
    client: Any,
    *,
    bass_track_index: int,
    drums_track_index: int,
    scene_index: int,
    style: str,
    seed: int,
    sustain_bass: bool,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
) -> AccompanimentClipsResult:
    """Analyse ``path`` and create a bass clip and a drum clip in empty slots.

    Everything that can fail without Live — track choice, analysis, metre,
    generation, payload validation — happens before the bridge is contacted.
    Then a preflight reads the session and both target slots and refuses a
    missing or non-MIDI track, a missing scene and any occupied slot. Only
    after that are the two clips created with ``create_midi_clip``, which
    itself refuses an occupied slot, so nothing in the set is ever
    overwritten. If the drum clip fails after the bass clip was created, the
    error says so; the bass clip is left in place for the user to keep or
    delete.
    """
    if bass_track_index == drums_track_index:
        raise ValueError("Bass and drums need two different tracks.")
    analysis = _analyze(path, beats_per_bar, tempo_hint)
    if analysis.time_signature != _BRIDGE_TIME_SIGNATURE:
        raise ValueError(
            f"The recording was read as {analysis.time_signature}, but Ableton clips "
            "can only be created in 4/4. Pass beats_per_bar=4 if it is really in "
            "4/4, or use generate_accompaniment_from_audio to get MIDI files."
        )
    accompaniment = generate_accompaniment(
        analysis, style=style, seed=seed, sustain_bass=sustain_bass
    )
    parts = (
        ("bass", bass_track_index, composition_to_payload(accompaniment.bass)),
        ("drums", drums_track_index, composition_to_payload(accompaniment.drums)),
    )
    for _, _, payload in parts:
        validate_payload_v1(payload)

    _preflight(client, [track for _, track, _ in parts], scene_index)

    created: dict[str, InsertedPartResult] = {}
    for name, track, payload in parts:
        try:
            result = client.create_midi_clip(track, scene_index, payload)
        except AbletonError as error:
            if not created:
                raise
            raise AbletonError(
                f"The bass clip was created at track {bass_track_index}, scene "
                f"{scene_index}, but the {name} clip failed: {error}. Nothing was "
                "overwritten; keep or delete the bass clip."
            ) from error
        created[name] = InsertedPartResult(
            track_index=track,
            scene_index=scene_index,
            clip_length_beats=result["clip_length_beats"],
            note_count=result["note_count"],
        )

    request = accompaniment.bass.request
    downbeat = round(analysis.grid.first_downbeat_seconds, 4)
    return AccompanimentClipsResult(
        summary=analysis.summary(),
        style=style,
        seed=seed,
        bars=request.bars,
        tempo_bpm=round(analysis.tempo_bpm, 2),
        rounded_bpm=request.bpm,
        root_note=request.root_note,
        scale=request.scale,
        first_downbeat_seconds=downbeat,
        bass=created["bass"],
        drums=created["drums"],
        warnings=list(accompaniment.bass.report.warnings),
        alignment=(
            f"The clips start on bar 1 and run {request.bars} bars in beats. To play "
            f"them with the recording, set the Live tempo to about "
            f"{round(analysis.tempo_bpm, 2)} BPM (or warp the audio) and start the "
            f"audio clip at its first downbeat, {downbeat} s into the file."
        ),
    )


def _preflight(client: Any, tracks: list[int], scene_index: int) -> None:
    """Refuse targets that do not exist, cannot hold MIDI or are occupied."""
    session = client.get_session_state()
    by_index = {track["index"]: track for track in session.get("tracks", [])}
    scenes = {scene["index"] for scene in session.get("scenes", [])}
    if scene_index not in scenes:
        raise ValueError(f"Scene {scene_index} does not exist.")
    for track in tracks:
        if track not in by_index:
            raise ValueError(f"Track {track} does not exist.")
        if not by_index[track].get("can_hold_midi"):
            raise ValueError(f"Track {track} cannot hold MIDI clips.")
        try:
            client.get_midi_clip(track, scene_index)
        except AbletonCommandError as error:
            if error.code == "CLIP_NOT_FOUND":
                continue
            if error.code == "CLIP_NOT_MIDI":
                raise ValueError(
                    f"Track {track}, scene {scene_index} already holds an audio clip."
                ) from error
            raise
        raise ValueError(
            f"Track {track}, scene {scene_index} already holds a clip; choose an "
            "empty slot."
        )


def _analyze(
    path: str, beats_per_bar: int | None, tempo_hint: float | None
) -> MusicAnalysis:
    from midi_generator.audio import analyze_audio

    return analyze_audio(path, beats_per_bar=beats_per_bar, tempo_hint=tempo_hint)
