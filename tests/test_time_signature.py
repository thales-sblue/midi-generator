"""Coverage for variable time signatures (Ciclo 3).

The ``TimeSignature`` value object plus its propagation through the heuristic
generator, the contextual generator, the Integration Payload v1 metadata, the
MIDI exporter and the CLI. The Ableton bridge stays 4/4-only.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from mido import MidiFile

from ableton_remote_script.MidiGeneratorBridge.bridge_core import (
    BridgeCommandError,
    payload_to_clip_data,
)
from midi_generator.domain import MelodyRequest, NoteEvent, TimeSignature
from midi_generator.domain.music_theory import ROOT_NOTES, SCALE_INTERVALS
from midi_generator.exporters import MidiExporter
from midi_generator.generation import generate_contextual_plan, generate_plan
from midi_generator.integration import composition_to_payload
from midi_generator.transformations import EditableMidiClip

TICKS_PER_BEAT = 480


def _pitch_classes(root_note: str, scale: str) -> set[int]:
    root = ROOT_NOTES[root_note.upper()]
    return {(root + interval) % 12 for interval in SCALE_INTERVALS[scale]}


# --- TimeSignature value object ------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4/4", TimeSignature(4, 4)),
        ("3/4", TimeSignature(3, 4)),
        ("6/8", TimeSignature(6, 8)),
        (" 12/8 ", TimeSignature(12, 8)),
    ],
)
def test_parse_accepts_well_formed_meters(text, expected):
    assert TimeSignature.parse(text) == expected


@pytest.mark.parametrize("text", ["4", "4-4", "4/4/4", "x/4", "4/y", "", "/", "4/3"])
def test_parse_rejects_malformed_or_unsupported_meters(text):
    with pytest.raises(ValueError):
        TimeSignature.parse(text)


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [(0, 4), (-1, 4), (4, 3), (4, 5), (4, 0), (4, 32)],
)
def test_construction_rejects_invalid_components(numerator, denominator):
    with pytest.raises(ValueError):
        TimeSignature(numerator, denominator)


@pytest.mark.parametrize(
    ("meter", "bar_ticks"),
    [("4/4", 1920), ("3/4", 1440), ("6/8", 1440), ("12/8", 2880), ("2/2", 1920)],
)
def test_bar_ticks_matches_note_value_math(meter, bar_ticks):
    assert TimeSignature.parse(meter).bar_ticks(TICKS_PER_BEAT) == bar_ticks


def test_bar_ticks_rejects_a_fractional_result():
    # 7/16 at one tick per beat cannot be expressed in whole ticks.
    with pytest.raises(ValueError):
        TimeSignature(7, 16).bar_ticks(1)


def test_time_signature_is_hashable_and_stringifies():
    assert str(TimeSignature(6, 8)) == "6/8"
    assert {TimeSignature(3, 4), TimeSignature(3, 4)} == {TimeSignature(3, 4)}


# --- MelodyRequest default ----------------------------------------------------


def test_request_defaults_to_four_four():
    assert MelodyRequest(120, "C", "major", 4, 1).time_signature == TimeSignature(4, 4)


def test_request_validate_rejects_a_non_time_signature():
    request = MelodyRequest(120, "C", "major", 4, 1, time_signature="3/4")
    with pytest.raises(ValueError):
        request.validate()


# --- Heuristic generator ----------------------------------------------------


def test_omitted_meter_is_bit_identical_to_explicit_four_four():
    omitted = generate_plan(MelodyRequest(120, "C", "major", 4, 42))
    explicit = generate_plan(
        MelodyRequest(120, "C", "major", 4, 42, TimeSignature(4, 4))
    )
    assert omitted == explicit


@pytest.mark.parametrize("meter", ["3/4", "6/8", "12/8", "7/8"])
def test_generate_plan_honours_the_requested_meter(meter):
    time_signature = TimeSignature.parse(meter)
    request = MelodyRequest(120, "A", "minor", 8, 2026, time_signature)

    plan = generate_plan(request)

    expected_ticks = 8 * time_signature.bar_ticks(TICKS_PER_BEAT)
    assert plan.total_duration_ticks == expected_ticks
    assert plan.report.duration_ticks == expected_ticks
    assert plan.notes
    assert all(
        note.start >= 0 and note.start + note.duration <= expected_ticks
        for note in plan.notes
    )
    assert {note.pitch % 12 for note in plan.notes} <= _pitch_classes("A", "minor")
    assert generate_plan(request).notes == plan.notes


def test_generate_plan_metadata_and_payload_carry_the_meter_string():
    plan = generate_plan(
        MelodyRequest(128, "F#", "major", 3, 7, TimeSignature(3, 4))
    )
    assert plan.metadata["time_signature"] == "3/4"
    assert composition_to_payload(plan)["time_signature"] == "3/4"


def test_three_four_and_six_eight_share_a_bar_length_but_both_generate():
    three_four = generate_plan(MelodyRequest(120, "C", "major", 4, 5, TimeSignature(3, 4)))
    six_eight = generate_plan(MelodyRequest(120, "C", "major", 4, 5, TimeSignature(6, 8)))
    assert three_four.total_duration_ticks == six_eight.total_duration_ticks == 4 * 1440


def test_generate_plan_rejects_a_meter_off_the_eighth_note_grid():
    with pytest.raises(ValueError):
        generate_plan(MelodyRequest(120, "C", "major", 1, 1, TimeSignature(3, 16)))


# --- Contextual generator ----------------------------------------------------


def test_contextual_generation_honours_the_requested_meter():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=tuple(
            NoteEvent(pitch, index * 240, 240, 88)
            for index, pitch in enumerate((62, 65, 69, 67, 64, 62, 60, 65))
        ),
    )
    request = MelodyRequest(120, "D", "dorian", 2, 7, TimeSignature(3, 4))

    plan = generate_contextual_plan(request, reference)

    assert plan.total_duration_ticks == 2 * 1440
    assert plan.metadata["time_signature"] == "3/4"
    assert plan.notes
    assert {note.pitch % 12 for note in plan.notes} <= _pitch_classes("D", "dorian")
    assert all(
        note.start + note.duration <= plan.total_duration_ticks for note in plan.notes
    )
    assert generate_contextual_plan(request, reference).notes == plan.notes


# --- Exporter --------------------------------------------------------------


def test_exporter_emits_a_time_signature_meta_message(tmp_path):
    plan = generate_plan(MelodyRequest(120, "C", "major", 2, 3, TimeSignature(6, 8)))

    midi = MidiFile(MidiExporter().export(plan, tmp_path / "six_eight.mid"))

    meta = [m for m in midi.tracks[0] if m.type == "time_signature"]
    assert len(meta) == 1
    assert (meta[0].numerator, meta[0].denominator) == (6, 8)
    assert sum(message.time for message in midi.tracks[0]) == plan.total_duration_ticks


# --- Ableton bridge stays 4/4-only ----------------------------------------


def test_bridge_still_refuses_a_generated_non_four_four_payload():
    payload = composition_to_payload(
        generate_plan(MelodyRequest(120, "C", "minor", 2, 42, TimeSignature(3, 4)))
    )
    with pytest.raises(BridgeCommandError) as caught:
        payload_to_clip_data(payload)
    assert caught.value.code == "UNSUPPORTED_TIME_SIGNATURE"


# --- CLI ------------------------------------------------------------------


def _run_cli(tmp_path, *extra):
    output = tmp_path / "cli.mid"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable, "-m", "midi_generator",
            "--bpm", "120", "--root", "C", "--scale", "major",
            "--bars", "2", "--seed", "5", "--output", str(output), *extra,
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    return result, output


def test_cli_accepts_a_time_signature_flag(tmp_path):
    result, output = _run_cli(tmp_path, "--time-signature", "6/8")
    assert result.returncode == 0, result.stderr
    assert output.exists()
    midi = MidiFile(output)
    meta = [m for m in midi.tracks[0] if m.type == "time_signature"]
    assert (meta[0].numerator, meta[0].denominator) == (6, 8)


def test_cli_rejects_a_malformed_time_signature(tmp_path):
    result, output = _run_cli(tmp_path, "--time-signature", "not-a-meter")
    assert result.returncode != 0
    assert not output.exists()
