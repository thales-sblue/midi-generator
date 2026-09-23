"""Write an accompaniment (bass + drums) and the analysis it came from."""

import json
from dataclasses import dataclass
from pathlib import Path

from midi_generator.domain import MusicAnalysis
from midi_generator.generation import Accompaniment

from .midi_exporter import MidiExporter


@dataclass(frozen=True)
class AccompanimentFiles:
    bass: Path
    drums: Path
    analysis: Path


def export_accompaniment(
    accompaniment: Accompaniment,
    analysis: MusicAnalysis,
    folder: str | Path,
    stem: str,
    *,
    follow_recording: bool = True,
) -> AccompanimentFiles:
    """Write ``<stem>.bass.mid``, ``<stem>.drums.mid`` and ``<stem>.analysis.json``.

    With ``follow_recording`` (default) both MIDI files carry the analysis
    tempo map and start with the recording's lead-in, so they line up with the
    audio when both start at time 0. Without it they start at bar 1 at the
    plan's rounded tempo.
    """
    folder = Path(folder)
    tempo_map = accompaniment.tempo_map if follow_recording else None
    exporter = MidiExporter()
    bass = exporter.export(accompaniment.bass, folder / f"{stem}.bass.mid", tempo_map=tempo_map)
    drums = exporter.export(
        accompaniment.drums, folder / f"{stem}.drums.mid", tempo_map=tempo_map
    )
    report = folder / f"{stem}.analysis.json"
    report.write_text(json.dumps(analysis.to_dict(), indent=2) + "\n", encoding="utf-8")
    return AccompanimentFiles(bass=bass, drums=drums, analysis=report)
