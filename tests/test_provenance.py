import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from midi_generator.domain import MelodyRequest, NoteEvent
from midi_generator.generation import generate_contextual_plan, generate_plan
from midi_generator.integration import composition_to_payload
from midi_generator.provenance import (
    CONTEXTUAL_BACKEND,
    HEURISTIC_BACKEND,
    PROVENANCE_SCHEMA_VERSION,
    build_manifest,
    hash_clip,
    hash_notes,
    validate_manifest,
)
from midi_generator.transformations import EditableMidiClip

_TIMESTAMP = "2026-08-31T12:00:00+00:00"


def _request(seed: int = 2026) -> MelodyRequest:
    return MelodyRequest(120, "C", "minor", 4, seed)


def _reference() -> EditableMidiClip:
    return EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 90),
            NoteEvent(64, 480, 480, 90),
            NoteEvent(67, 960, 480, 90),
            NoteEvent(64, 1440, 480, 90),
        ),
    )


# --- hashing --------------------------------------------------------------


def test_hash_notes_is_deterministic():
    plan = generate_plan(_request(5))
    assert hash_notes(plan.notes, plan.total_duration_ticks) == hash_notes(
        plan.notes, plan.total_duration_ticks
    )


def test_hash_notes_is_sensitive_to_content_and_order():
    a = NoteEvent(60, 0, 240, 80)
    b = NoteEvent(62, 240, 240, 80)
    base = hash_notes((a, b), 480)
    assert base != hash_notes((b, a), 480)
    assert base != hash_notes((a, NoteEvent(63, 240, 240, 80)), 480)
    assert base != hash_notes((a, b), 960)


def test_hash_clip_matches_hash_notes():
    clip = _reference()
    assert hash_clip(clip) == hash_notes(clip.notes, clip.length_ticks)


# --- build_manifest ------------------------------------------------------


def test_manifest_for_heuristic_plan():
    plan = generate_plan(_request(2026))
    manifest = build_manifest(plan, generated_at=_TIMESTAMP)
    assert manifest.provenance_schema_version == PROVENANCE_SCHEMA_VERSION
    assert manifest.backend == HEURISTIC_BACKEND
    assert manifest.backend_version == "1.0.0"
    assert manifest.seed == 2026
    assert manifest.context_hash is None
    assert manifest.output_hash == hash_notes(
        plan.notes, plan.total_duration_ticks
    )
    assert manifest.parameters == {
        "bpm": 120,
        "root_note": "C",
        "scale": "minor",
        "bars": 4,
        "time_signature": "4/4",
    }
    assert manifest.generated_at == _TIMESTAMP


def test_manifest_is_deterministic():
    plan = generate_plan(_request(7))
    assert build_manifest(plan, generated_at=_TIMESTAMP) == build_manifest(
        plan, generated_at=_TIMESTAMP
    )


def test_manifest_for_contextual_plan_hashes_reference():
    reference = _reference()
    plan = generate_contextual_plan(_request(11), reference)
    manifest = build_manifest(
        plan, generated_at=_TIMESTAMP, reference=reference
    )
    assert manifest.backend == CONTEXTUAL_BACKEND
    assert manifest.context_hash == hash_clip(reference)


def test_manifest_rejects_non_iso_timestamp():
    plan = generate_plan(_request(1))
    with pytest.raises(ValueError):
        build_manifest(plan, generated_at="last thursday")
    with pytest.raises(ValueError):
        build_manifest(plan, generated_at="")


def test_manifest_dict_is_json_safe_and_valid():
    plan = generate_plan(_request(3))
    manifest = build_manifest(plan, generated_at=_TIMESTAMP)
    encoded = json.dumps(manifest.to_dict())
    validate_manifest(json.loads(encoded))


# --- validate_manifest -------------------------------------------------


def _valid_manifest_dict() -> dict:
    plan = generate_plan(_request(9))
    return build_manifest(plan, generated_at=_TIMESTAMP).to_dict()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.pop("output_hash"),
        lambda m: m.__setitem__("provenance_schema_version", 2),
        lambda m: m.__setitem__("backend", "transformer"),
        lambda m: m["parameters"].pop("time_signature"),
        lambda m: m.__setitem__("seed", "2026"),
        lambda m: m.__setitem__("generated_at", ""),
    ],
)
def test_validate_manifest_rejects_broken_dicts(mutate):
    manifest = _valid_manifest_dict()
    mutate(manifest)
    with pytest.raises(ValueError):
        validate_manifest(manifest)


# --- kept beside Payload v1, never inside -----------------------------


def test_payload_v1_carries_no_provenance():
    payload = composition_to_payload(generate_plan(_request(2)))
    assert "provenance_schema_version" not in payload
    assert "output_hash" not in payload
    assert "provenance" not in payload


# --- CLI --------------------------------------------------------------


def _run_cli(tmp_path: Path, *extra: str):
    output = tmp_path / "cli.mid"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "midi_generator",
            "--bpm",
            "120",
            "--root",
            "C",
            "--scale",
            "minor",
            "--bars",
            "4",
            "--seed",
            "2026",
            "--output",
            str(output),
            *extra,
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    return result, tmp_path


def test_cli_writes_provenance_manifest(tmp_path):
    result, workdir = _run_cli(tmp_path, "--provenance")
    assert result.returncode == 0, result.stderr
    manifest_path = workdir / "cli.mid.provenance.json"
    assert manifest_path.exists()
    validate_manifest(json.loads(manifest_path.read_text()))


def test_cli_without_flag_writes_no_manifest(tmp_path):
    result, workdir = _run_cli(tmp_path)
    assert result.returncode == 0, result.stderr
    assert not list(workdir.glob("*.provenance.json"))


def test_cli_candidates_write_one_manifest_each(tmp_path):
    result, workdir = _run_cli(tmp_path, "--candidates", "3", "--provenance")
    assert result.returncode == 0, result.stderr
    manifests = sorted(workdir.glob("cli_rank*_seed*.mid.provenance.json"))
    assert len(manifests) == 3
    for manifest_path in manifests:
        validate_manifest(json.loads(manifest_path.read_text()))
