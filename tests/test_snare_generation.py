"""Deterministic snare backbeat that follows a reference clip's metre."""

import pytest

from midi_generator.domain import MelodyRequest, NoteEvent, TimeSignature
from midi_generator.generation import generate_snare_plan
from midi_generator.generation.drums import SNARE_DURATION_TICKS, SNARE_PITCH
from midi_generator.integration import (
    composition_to_payload,
    validate_payload_v1,
)
from midi_generator.transformations import EditableMidiClip


def reference_clip(length_ticks=1920):
    """A clip whose own onsets are irrelevant to the backbeat grid."""
    return EditableMidiClip(
        length_ticks=length_ticks,
        notes=(NoteEvent(60, 0, length_ticks, 70),),
    )


def request(bars=1, seed=42, time_signature=None):
    kwargs = {}
    if time_signature is not None:
        kwargs["time_signature"] = time_signature
    return MelodyRequest(120, "C", "major", bars, seed, **kwargs)


def test_snare_lands_on_beats_two_and_four_in_4_4():
    plan = generate_snare_plan(request(), reference_clip())

    assert [(n.pitch, n.start, n.velocity) for n in plan.notes] == [
        (SNARE_PITCH, 480, 100),
        (SNARE_PITCH, 1440, 100),
    ]
    assert plan.total_duration_ticks == 1920
    assert plan.report.note_count == 2
    assert plan.report.pause_count == 0
    assert plan.metadata["generation_mode"] == "snare"
    assert plan.metadata["placement"] == "backbeat"
    assert plan.metadata["snare_count"] == 2
    assert plan.metadata["snare_pitch"] == SNARE_PITCH
    assert plan.metadata["reference_length_ticks"] == 1920


def test_snare_ignores_reference_onsets_entirely():
    silent = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(60, 0, 480, 70, mute=True),),
    )

    plan = generate_snare_plan(request(), silent)

    assert [n.start for n in plan.notes] == [480, 1440]


def test_snare_repeats_the_backbeat_across_bars():
    plan = generate_snare_plan(request(bars=2), reference_clip(3840))

    assert [n.start for n in plan.notes] == [480, 1440, 2400, 3360]
    assert plan.metadata["snare_count"] == 4


def test_snare_places_only_beat_two_in_3_4():
    plan = generate_snare_plan(
        request(time_signature=TimeSignature(3, 4)), reference_clip(1440)
    )

    assert [n.start for n in plan.notes] == [480]
    assert plan.metadata["snare_count"] == 1


def test_snare_duration_clamps_to_next_snare_and_to_clip_end():
    plan = generate_snare_plan(request(bars=2), reference_clip(3840))

    durations = [n.duration for n in plan.notes]
    assert durations == [
        SNARE_DURATION_TICKS,
        SNARE_DURATION_TICKS,
        SNARE_DURATION_TICKS,
        SNARE_DURATION_TICKS,
    ]
    assert all(n.start + n.duration <= plan.total_duration_ticks for n in plan.notes)


def test_snare_is_deterministic_and_carries_seed_to_report_only():
    reference = reference_clip()
    first = generate_snare_plan(request(seed=1), reference)
    same = generate_snare_plan(request(seed=1), reference)
    other_seed = generate_snare_plan(request(seed=999), reference)

    assert first == same
    assert first.notes == other_seed.notes
    assert first.report.seed == 1
    assert other_seed.report.seed == 999
    assert reference == reference_clip()


def test_snare_plan_serializes_to_integration_payload_v1():
    payload = composition_to_payload(generate_snare_plan(request(), reference_clip()))

    validate_payload_v1(payload)
    assert payload["schema_version"] == 1
    assert {note["pitch"] for note in payload["notes"]} == {SNARE_PITCH}
    assert payload["metadata"]["generation_mode"] == "snare"


def test_snare_rejects_length_mismatch_between_request_and_reference():
    with pytest.raises(ValueError, match="reference clip length"):
        generate_snare_plan(request(bars=2), reference_clip())


def test_snare_rejects_time_signatures_with_fewer_than_two_beats_per_bar():
    with pytest.raises(ValueError, match="at least two beats per bar"):
        generate_snare_plan(
            request(time_signature=TimeSignature(1, 4)), reference_clip(480)
        )


@pytest.mark.parametrize("velocity", [0, 128, -1, True, 1.5])
def test_snare_rejects_out_of_range_velocity(velocity):
    with pytest.raises(ValueError, match="velocity must be"):
        generate_snare_plan(request(), reference_clip(), velocity=velocity)
