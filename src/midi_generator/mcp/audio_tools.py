"""MCP orchestration for audio analysis and accompaniment files.

No musical decision is made here: the analysis comes from
``midi_generator.audio``, the parts from ``generation.accompaniment`` and the
files from ``exporters``. The audio package is imported lazily so the MCP
server starts without loading librosa until an audio tool is called.
"""

from pathlib import Path
from typing import Any, TypedDict

from midi_generator.domain import MusicAnalysis
from midi_generator.exporters import export_accompaniment
from midi_generator.generation import generate_accompaniment

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


def _analyze(
    path: str, beats_per_bar: int | None, tempo_hint: float | None
) -> MusicAnalysis:
    from midi_generator.audio import analyze_audio

    return analyze_audio(path, beats_per_bar=beats_per_bar, tempo_hint=tempo_hint)
