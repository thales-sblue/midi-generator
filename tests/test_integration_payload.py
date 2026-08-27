import json
from copy import deepcopy
from dataclasses import replace

import pytest

from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import (
    SCHEMA_VERSION,
    composition_to_payload,
    validate_payload_v1,
)


REQUIRED_FIELDS = {
    "schema_version",
    "bpm",
    "root_note",
    "scale",
    "bars",
    "seed",
    "time_signature",
    "ticks_per_beat",
    "total_duration_ticks",
    "notes",
    "report",
    "metadata",
}


def test_composition_plan_serializes_to_versioned_payload():
    plan = generate_plan(MelodyRequest(120, "C", "minor", 2, 42))

    payload = composition_to_payload(plan)

    assert payload["schema_version"] == SCHEMA_VERSION == 1
    assert payload["bpm"] == 120
    assert payload["root_note"] == "C"
    assert payload["scale"] == "minor"
    assert payload["bars"] == 2
    assert payload["seed"] == 42
    assert payload["time_signature"] == "4/4"
    assert payload["ticks_per_beat"] == 480
    assert payload["total_duration_ticks"] == plan.total_duration_ticks
    assert REQUIRED_FIELDS.issubset(payload)


def test_payload_preserves_every_note_and_report_field():
    plan = generate_plan(MelodyRequest(128, "F#", "major", 3, 2026))

    payload = composition_to_payload(plan)

    assert payload["notes"] == [
        {
            "pitch": note.pitch,
            "start": note.start,
            "duration": note.duration,
            "velocity": note.velocity,
            "channel": note.channel,
            "track": note.track,
        }
        for note in plan.notes
    ]
    assert payload["report"] == {
        "note_count": plan.report.note_count,
        "pause_count": plan.report.pause_count,
        "duration_ticks": plan.report.duration_ticks,
        "scale": plan.report.scale,
        "seed": plan.report.seed,
        "warnings": list(plan.report.warnings),
    }


def test_payload_is_json_safe_and_deterministic():
    request = MelodyRequest(110, "Bb", "minor", 4, 7)

    first = composition_to_payload(generate_plan(request))
    second = composition_to_payload(generate_plan(request))

    assert first == second
    round_trip = json.loads(json.dumps(first))
    assert round_trip == first
    assert round_trip["time_signature"] == "4/4"
    assert round_trip["ticks_per_beat"] == 480


@pytest.mark.parametrize("missing_field", ["time_signature", "ticks_per_beat"])
def test_serializer_rejects_plan_without_required_timing(missing_field):
    plan = generate_plan(MelodyRequest(120, "C", "major", 1, 1))
    metadata = dict(plan.metadata)
    metadata.pop(missing_field)

    with pytest.raises(ValueError, match=missing_field):
        composition_to_payload(replace(plan, metadata=metadata))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(schema_version=2), "schema_version"),
        (lambda payload: payload.update(bpm=10), "BPM"),
        (lambda payload: payload.update(bars=0), "Bars"),
        (lambda payload: payload.update(time_signature=""), "time_signature"),
        (lambda payload: payload.update(ticks_per_beat=0), "ticks_per_beat"),
        (
            lambda payload: payload.update(total_duration_ticks=0),
            "total_duration_ticks",
        ),
        (lambda payload: payload["notes"][0].pop("pitch"), "missing required"),
        (lambda payload: payload["notes"][0].update(pitch=128), "pitch"),
        (lambda payload: payload["notes"][0].update(velocity=0), "velocity"),
        (lambda payload: payload["notes"][0].update(duration=0), "duration"),
        (lambda payload: payload["notes"][0].update(start=-1), "start"),
    ],
)
def test_payload_v1_validation_rejects_invalid_contract(mutation, message):
    valid = composition_to_payload(
        generate_plan(MelodyRequest(120, "C", "minor", 4, 42))
    )
    invalid = deepcopy(valid)
    mutation(invalid)

    with pytest.raises(ValueError, match=message):
        validate_payload_v1(invalid)
