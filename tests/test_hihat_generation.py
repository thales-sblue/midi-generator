"""Deterministic closed hi-hat on a steady subdivision of the beat."""

import pytest

from midi_generator.domain import MelodyRequest, NoteEvent, TimeSignature
from midi_generator.generation import generate_hihat_plan
from midi_generator.generation.drums import HIHAT_DURATION_TICKS, HIHAT_PITCH
from midi_generator.integration import composition_to_payload, validate_payload_v1
from midi_generator.transformations import EditableMidiClip


def reference(bars=1, bar_ticks=1920, notes=()):
    return EditableMidiClip(length_ticks=bars * bar_ticks, notes=tuple(notes))


def request(bars=1, seed=7, time_signature=None):
    return MelodyRequest(
        120, "A", "minor", bars, seed, time_signature or TimeSignature(4, 4)
    )


def test_hihat_defaults_to_eighth_notes():
    plan = generate_hihat_plan(request(), reference())

    assert [n.start for n in plan.notes] == list(range(0, 1920, 240))
    assert {n.pitch for n in plan.notes} == {HIHAT_PITCH}
    assert {n.velocity for n in plan.notes} == {80}
    assert all(n.duration == HIHAT_DURATION_TICKS for n in plan.notes)
    assert plan.report.note_count == 8
    assert plan.metadata["generation_mode"] == "hihat"
    assert plan.metadata["subdivision"] == 2
    assert plan.metadata["hihat_count"] == 8


@pytest.mark.parametrize(
    ("subdivision", "step", "duration"), [(1, 480, 120), (4, 120, 120)]
)
def test_hihat_subdivisions(subdivision, step, duration):
    plan = generate_hihat_plan(request(bars=2), reference(bars=2), subdivision=subdivision)

    assert [n.start for n in plan.notes] == list(range(0, 3840, step))
    assert all(n.duration == duration for n in plan.notes)


def test_hihat_ignores_reference_onsets_and_key():
    busy = reference(notes=[NoteEvent(61, 100, 50, 90), NoteEvent(30, 700, 50, 90)])
    in_other_key = MelodyRequest(120, "F#", "blues", 1, 7)

    assert generate_hihat_plan(request(), busy).notes == generate_hihat_plan(
        in_other_key, reference()
    ).notes


def test_hihat_follows_the_metre():
    plan = generate_hihat_plan(
        request(bars=2, time_signature=TimeSignature(3, 4)), reference(2, 1440)
    )
    assert len(plan.notes) == 12
    assert plan.metadata["time_signature"] == "3/4"


def test_hihat_is_deterministic_and_carries_the_seed():
    first = generate_hihat_plan(request(seed=3), reference(), velocity=64)
    assert first == generate_hihat_plan(request(seed=3), reference(), velocity=64)
    assert first.report.seed == 3
    assert {n.velocity for n in first.notes} == {64}


@pytest.mark.parametrize("subdivision", [0, 3, 8, True, "2"])
def test_hihat_rejects_an_unknown_subdivision(subdivision):
    with pytest.raises(ValueError, match="subdivision must be one of"):
        generate_hihat_plan(request(), reference(), subdivision=subdivision)


@pytest.mark.parametrize("velocity", [0, 128, 64.0, True])
def test_hihat_rejects_invalid_velocity(velocity):
    with pytest.raises(ValueError, match="velocity"):
        generate_hihat_plan(request(), reference(), velocity=velocity)


def test_hihat_requires_matching_length():
    with pytest.raises(ValueError, match="reference clip length"):
        generate_hihat_plan(request(bars=2), reference())


def test_hihat_plan_serializes_to_payload_v1():
    payload = composition_to_payload(generate_hihat_plan(request(), reference()))
    validate_payload_v1(payload)
    assert len(payload["notes"]) == 8
