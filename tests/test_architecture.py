import os
from pathlib import Path
import subprocess
import sys

from mido import MidiFile

from midi_generator.domain import MelodyRequest, NoteEvent
from midi_generator.exporters import MidiExporter
from midi_generator.generation.melody import BEATS_PER_BAR, TICKS_PER_BEAT, generate_plan


def test_melody_request_is_valid():
    request = MelodyRequest(140, "F#", "minor", 8, 2026)
    request.validate()
    assert request.seed == 2026


def test_plan_is_deterministic_for_same_seed():
    request = MelodyRequest(120, "C", "major", 4, 42)
    assert generate_plan(request) == generate_plan(request)


def test_plan_contains_valid_note_events():
    plan = generate_plan(MelodyRequest(120, "F#", "minor", 4, 7))
    assert plan.notes
    assert all(isinstance(note, NoteEvent) for note in plan.notes)
    assert all(note.start >= 0 and note.duration > 0 for note in plan.notes)
    assert all(1 <= note.velocity <= 127 for note in plan.notes)


def test_plan_duration_and_report_match_requested_bars():
    plan = generate_plan(MelodyRequest(120, "C", "major", 3, 9))
    expected = 3 * BEATS_PER_BAR * TICKS_PER_BEAT
    assert plan.total_duration_ticks == expected
    assert plan.report.duration_ticks == expected
    assert plan.report.note_count == len(plan.notes)
    assert plan.report.seed == plan.seed


def test_exporter_writes_valid_midi(tmp_path):
    plan = generate_plan(MelodyRequest(110, "A", "minor", 2, 15))
    result = MidiExporter().export(plan, tmp_path / "plan.mid")
    midi = MidiFile(result)
    assert result.exists()
    assert sum(message.time for message in midi.tracks[0]) == plan.total_duration_ticks


def test_cli_remains_usable(tmp_path):
    output = tmp_path / "cli.mid"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "midi_generator", "--bpm", "120", "--root", "C", "--scale", "major", "--bars", "2", "--seed", "5", "--output", str(output)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
