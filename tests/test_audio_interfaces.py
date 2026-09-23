"""CLI and MCP entry points for audio analysis and accompaniment."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client
from mido import MidiFile

from audio_synthesis import strummed_progression, write_wav
from midi_generator.mcp import audio_tools
from midi_generator.mcp.server import mcp

PROJECT_ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def recording(tmp_path_factory):
    folder = tmp_path_factory.mktemp("interfaces")
    return write_wav(
        folder / "take.wav", strummed_progression(("Am", "F", "C", "G"), bpm=96)
    )


def _run_cli(*args):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "midi_generator.audio", *map(str, args)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def test_cli_analyze_prints_a_lead_sheet_and_json(recording):
    text = _run_cli("analyze", recording)
    assert text.returncode == 0, text.stderr
    assert "Bar 1: Am" in text.stdout
    assert "Bar 4: G" in text.stdout

    as_json = _run_cli("analyze", recording, "--json")
    assert as_json.returncode == 0, as_json.stderr
    data = json.loads(as_json.stdout)
    assert data["schema"] == "music_analysis"
    assert [m["chord"] for m in data["measures"]][:4] == ["Am", "F", "C", "G"]
    assert data["tempo"] == pytest.approx(96, abs=2)


def test_cli_accompany_writes_bass_drums_and_analysis(recording, tmp_path):
    result = _run_cli("accompany", recording, "--output-dir", tmp_path)
    assert result.returncode == 0, result.stderr
    bass, drums, report = (
        tmp_path / "take.bass.mid",
        tmp_path / "take.drums.mid",
        tmp_path / "take.analysis.json",
    )
    assert bass.exists() and drums.exists() and report.exists()
    # Following the recording means several tempo events, not one.
    tempos = [m for m in MidiFile(drums).tracks[0] if m.type == "set_tempo"]
    assert len(tempos) > 1
    assert "start them together with the audio" in result.stdout


def test_cli_accompany_constant_tempo_writes_one_tempo(recording, tmp_path):
    result = _run_cli("accompany", recording, "--output-dir", tmp_path, "--constant-tempo")
    assert result.returncode == 0, result.stderr
    tempos = [m for m in MidiFile(tmp_path / "take.drums.mid").tracks[0] if m.type == "set_tempo"]
    assert len(tempos) == 1
    assert "first downbeat" in result.stdout


def test_cli_reports_a_missing_file(tmp_path):
    result = _run_cli("analyze", tmp_path / "nope.wav")
    assert result.returncode == 1
    assert "not found" in result.stderr


def _call(tool, arguments):
    async def run():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool(tool, arguments)
            return {t.name for t in tools.tools}, result

    return asyncio.run(run())


def test_mcp_analyze_audio_file(recording):
    names, result = _call("analyze_audio_file", {"path": str(recording)})
    assert {"analyze_audio_file", "generate_accompaniment_from_audio"} <= names
    assert result.is_error is False
    content = result.structured_content
    assert "Bar 1: Am" in content["summary"]
    assert content["analysis"]["time_signature"] == "4/4"


def test_mcp_generate_accompaniment_writes_files(recording, tmp_path, monkeypatch):
    monkeypatch.setattr(audio_tools, "ACCOMPANIMENT_FOLDER", tmp_path)
    _, result = _call(
        "generate_accompaniment_from_audio", {"path": str(recording), "seed": 3}
    )
    assert result.is_error is False
    content = result.structured_content
    assert content["style"] == "basic"
    assert content["seed"] == 3
    assert content["bars"] >= 4
    assert (content["root_note"], content["scale"]) in {("A", "minor"), ("C", "major")}
    assert content["follows_recording"] is True
    assert Path(content["bass_midi_path"]).parent == tmp_path.resolve()
    assert Path(content["drums_midi_path"]).exists()
    assert Path(content["analysis_path"]).exists()


def test_mcp_reports_errors_as_tool_errors(tmp_path):
    _, missing = _call("analyze_audio_file", {"path": str(tmp_path / "nope.wav")})
    assert missing.is_error is True
    assert "not found" in missing.content[0].text
