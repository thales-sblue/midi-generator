import json

from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import SCHEMA_VERSION, composition_to_payload


def test_composition_plan_serializes_to_versioned_payload():
    plan = generate_plan(MelodyRequest(120, "C", "minor", 2, 42))

    payload = composition_to_payload(plan)

    assert payload["schema_version"] == SCHEMA_VERSION == 1
    assert payload["bpm"] == 120
    assert payload["root_note"] == "C"
    assert payload["scale"] == "minor"
    assert payload["bars"] == 2
    assert payload["seed"] == 42
    assert payload["total_duration_ticks"] == plan.total_duration_ticks


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
    assert json.loads(json.dumps(first)) == first
