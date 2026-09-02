"""Deterministic kick pattern that follows a reference clip's onsets."""

import pytest

from midi_generator.domain import MelodyRequest, NoteEvent
from midi_generator.generation import generate_kick_plan
from midi_generator.generation.drums import KICK_DURATION_TICKS, KICK_PITCH
from midi_generator.integration import (
    composition_to_payload,
    validate_payload_v1,
)
from midi_generator.transformations import EditableMidiClip


def reference_clip():
    """One 4/4 bar: notes on beats 1, 2 and 4; a chord on beat 2; a muted note."""
    return EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 70),
            NoteEvent(64, 480, 480, 80),
            NoteEvent(67, 480, 480, 80),
            NoteEvent(72, 1440, 480, 90),
            NoteEvent(48, 960, 240, 127, mute=True),
        ),
    )


def request(bars=1, seed=42):
    return MelodyRequest(120, "C", "major", bars, seed)


def test_kick_lands_once_on_each_distinct_sounding_onset():
    plan = generate_kick_plan(request(), reference_clip())

    assert [(n.pitch, n.start, n.velocity) for n in plan.notes] == [
        (KICK_PITCH, 0, 100),
        (KICK_PITCH, 480, 100),
        (KICK_PITCH, 1440, 100),
    ]
    assert plan.total_duration_ticks == 1920
    assert plan.report.note_count == 3
    assert plan.report.pause_count == 0
    assert plan.metadata["generation_mode"] == "kick"
    assert plan.metadata["onset_count"] == 3
    assert plan.metadata["kick_pitch"] == KICK_PITCH
    assert plan.metadata["reference_length_ticks"] == 1920


def test_kick_duration_clamps_to_next_onset_and_to_clip_end():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 120, 70),
            NoteEvent(64, 120, 480, 70),  # 120 ticks after the first onset
            NoteEvent(67, 1800, 120, 70),  # 120 ticks before the clip end
        ),
    )

    plan = generate_kick_plan(request(), reference)

    durations = [n.duration for n in plan.notes]
    assert durations == [120, KICK_DURATION_TICKS, 120]
    assert all(n.start + n.duration <= plan.total_duration_ticks for n in plan.notes)


def test_kick_ignores_muted_notes_entirely():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 240, 70),
            NoteEvent(62, 480, 240, 70, mute=True),
            NoteEvent(64, 960, 240, 70),
        ),
    )

    plan = generate_kick_plan(request(), reference)

    assert [n.start for n in plan.notes] == [0, 960]


def test_kick_is_deterministic_and_carries_seed_to_report_only():
    reference = reference_clip()
    first = generate_kick_plan(request(seed=1), reference)
    same = generate_kick_plan(request(seed=1), reference)
    other_seed = generate_kick_plan(request(seed=999), reference)

    assert first == same
    assert first.notes == other_seed.notes
    assert first.report.seed == 1
    assert other_seed.report.seed == 999
    assert reference == reference_clip()


def test_kick_plan_serializes_to_integration_payload_v1():
    payload = composition_to_payload(generate_kick_plan(request(), reference_clip()))

    validate_payload_v1(payload)
    assert payload["schema_version"] == 1
    assert {note["pitch"] for note in payload["notes"]} == {KICK_PITCH}
    assert payload["metadata"]["generation_mode"] == "kick"


def test_kick_rejects_length_mismatch_between_request_and_reference():
    with pytest.raises(ValueError, match="reference clip length"):
        generate_kick_plan(request(bars=2), reference_clip())


def test_kick_rejects_a_fully_muted_reference():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(60, 0, 480, 70, mute=True),),
    )

    with pytest.raises(ValueError, match="at least one sounding note"):
        generate_kick_plan(request(), reference)


@pytest.mark.parametrize("velocity", [0, 128, -1, True, 1.5])
def test_kick_rejects_out_of_range_velocity(velocity):
    with pytest.raises(ValueError, match="velocity must be"):
        generate_kick_plan(request(), reference_clip(), velocity=velocity)


def test_placement_defaults_to_per_onset():
    default = generate_kick_plan(request(), reference_clip())
    explicit = generate_kick_plan(
        request(), reference_clip(), placement="per_onset"
    )

    assert default == explicit
    assert default.metadata["placement"] == "per_onset"
    assert default.metadata["onset_source"] == "distinct sounding note starts"
    assert default.metadata["onset_count"] == 3
    assert default.metadata["kick_count"] == 3


def test_downbeat_only_places_one_kick_per_bar_ignoring_reference_onsets():
    plan = generate_kick_plan(
        request(bars=2), two_bar_reference(), placement="downbeat_only"
    )

    assert [n.start for n in plan.notes] == [0, 1920]
    assert {n.pitch for n in plan.notes} == {KICK_PITCH}
    assert plan.metadata["placement"] == "downbeat_only"
    assert plan.metadata["onset_source"] == "downbeat_only grid"
    assert plan.metadata["kick_count"] == 2
    assert plan.report.note_count == 2
    # onset_count still reports what the reference actually held.
    assert plan.metadata["onset_count"] == 3


def test_four_on_floor_places_one_kick_per_quarter_note():
    plan = generate_kick_plan(
        request(bars=2), two_bar_reference(), placement="four_on_floor"
    )

    assert [n.start for n in plan.notes] == [0, 480, 960, 1440, 1920, 2400, 2880, 3360]
    assert all(n.duration == KICK_DURATION_TICKS for n in plan.notes[:-1])
    assert plan.metadata["placement"] == "four_on_floor"
    assert plan.metadata["kick_count"] == 8


def test_grid_placements_do_not_require_a_sounding_reference():
    silent = EditableMidiClip(
        length_ticks=1920,
        notes=(NoteEvent(60, 0, 480, 70, mute=True),),
    )

    plan = generate_kick_plan(request(), silent, placement="four_on_floor")

    assert [n.start for n in plan.notes] == [0, 480, 960, 1440]
    assert plan.metadata["onset_count"] == 0


def test_grid_placements_are_deterministic():
    reference = two_bar_reference()
    first = generate_kick_plan(
        request(bars=2, seed=1), reference, placement="downbeat_only"
    )
    again = generate_kick_plan(
        request(bars=2, seed=1), reference, placement="downbeat_only"
    )

    assert first == again


def test_kick_rejects_an_unknown_placement():
    with pytest.raises(ValueError, match="placement must be one of"):
        generate_kick_plan(request(), reference_clip(), placement="backbeat")


def two_bar_reference():
    """Two 4/4 bars with onsets that never land on a bar downbeat."""
    return EditableMidiClip(
        length_ticks=3840,
        notes=(
            NoteEvent(60, 240, 240, 70),
            NoteEvent(64, 1200, 240, 70),
            NoteEvent(67, 2160, 240, 70),
        ),
    )
