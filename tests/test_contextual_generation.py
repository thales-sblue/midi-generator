import pytest

from midi_generator.domain import MelodyRequest, NoteEvent
from midi_generator.generation import generate_contextual_plan
from midi_generator.transformations import EditableMidiClip


def reference_clip():
    return EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 40),
            NoteEvent(64, 480, 480, 55),
            NoteEvent(67, 960, 480, 70),
            NoteEvent(65, 1440, 480, 80),
            NoteEvent(72, 0, 240, 127, mute=True),
        ),
    )


def test_contextual_generation_inherits_density_register_and_dynamics():
    reference = reference_clip()
    request = MelodyRequest(120, "C", "major", 2, 42)

    plan = generate_contextual_plan(request, reference)

    assert len(plan.notes) == 8
    assert all(60 <= note.pitch <= 67 for note in plan.notes)
    assert all(note.pitch % 12 in {0, 2, 4, 5, 7, 9, 11} for note in plan.notes)
    assert all(40 <= note.velocity <= 80 for note in plan.notes)
    assert all(note.start % 240 == 0 for note in plan.notes)
    assert all(
        current.start + current.duration <= following.start
        for current, following in zip(plan.notes, plan.notes[1:])
    )
    assert plan.metadata["generation_mode"] == "contextual"
    assert plan.metadata["reference_note_count"] == 4
    assert plan.metadata["reference_onset_count"] == 4
    assert plan.metadata["rhythm_sampling"] == (
        "reference_onset_phase_distribution"
    )
    assert plan.metadata["motion_sampling"] == (
        "reference_top_line_distribution"
    )
    assert reference == reference_clip()


def test_contextual_generation_is_reproducible_and_seed_sensitive():
    reference = reference_clip()
    request = MelodyRequest(120, "C", "major", 2, 42)

    first = generate_contextual_plan(request, reference)
    second = generate_contextual_plan(request, reference)
    changed = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 2, 43), reference
    )

    assert first == second
    assert first != changed


def test_contextual_generation_samples_reference_pitch_classes_and_velocities():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 240, 42),
            NoteEvent(72, 240, 240, 42),
            NoteEvent(60, 480, 240, 42),
            NoteEvent(64, 720, 240, 96),
            NoteEvent(67, 960, 240, 127, mute=True),
        ),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 4, 4), reference
    )

    assert {note.pitch % 12 for note in plan.notes} <= {0, 4}
    assert sum(note.pitch % 12 == 0 for note in plan.notes) == 15
    assert {note.velocity for note in plan.notes} <= {42, 96}
    assert plan.metadata["pitch_sampling"] == (
        "reference_pitch_class_distribution"
    )
    assert plan.metadata["velocity_sampling"] == "reference_values"


def test_contextual_generation_falls_back_when_scale_has_no_reference_pitch_class():
    reference = EditableMidiClip(
        length_ticks=960,
        notes=(
            NoteEvent(61, 0, 240, 50),
            NoteEvent(63, 240, 240, 90),
        ),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 1, 3), reference
    )

    assert all(note.pitch % 12 in {0, 2, 4, 5, 7, 9, 11} for note in plan.notes)
    assert {note.velocity for note in plan.notes} <= {50, 90}


@pytest.mark.parametrize(
    ("source_pitches", "direction"),
    [
        ((60, 62, 64, 65), 1),
        ((65, 64, 62, 60), -1),
    ],
)
def test_contextual_generation_inherits_top_line_motion(
    source_pitches, direction
):
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=tuple(
            NoteEvent(pitch, index * 480, 240, 90)
            for index, pitch in enumerate(source_pitches)
        ),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 2, 12), reference
    )

    intervals = tuple(
        following.pitch - current.pitch
        for current, following in zip(plan.notes, plan.notes[1:])
    )
    assert any(interval * direction > 0 for interval in intervals)
    assert all(interval * direction >= 0 for interval in intervals)


def test_contextual_generation_uses_nearest_scale_pitch_for_foreign_register():
    reference = EditableMidiClip(
        length_ticks=480,
        notes=(NoteEvent(66, 0, 480, 90),),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 1, 7), reference
    )

    assert {note.pitch for note in plan.notes} == {65}


def test_contextual_generation_uses_onsets_so_chords_do_not_inflate_density():
    reference = EditableMidiClip(
        length_ticks=480,
        notes=tuple(
            NoteEvent(pitch, 0, 480, 90) for pitch in (60, 64, 67, 72)
        ),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 1, 7), reference
    )

    assert len(plan.notes) == 4
    assert plan.metadata["reference_note_count"] == 4
    assert plan.metadata["reference_onset_count"] == 1
    assert plan.report.warnings == ()


def test_contextual_generation_inherits_onset_phases_on_eighth_note_grid():
    reference = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 120, 90),
            NoteEvent(62, 720, 120, 90),
            NoteEvent(64, 960, 120, 90),
            NoteEvent(65, 1680, 120, 90),
        ),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 2, 11), reference
    )

    assert len(plan.notes) == 8
    assert {note.start % 1920 for note in plan.notes} == {0, 720, 960, 1680}


def test_contextual_generation_caps_excessive_onset_density():
    reference = EditableMidiClip(
        length_ticks=480,
        notes=tuple(
            NoteEvent(60, start, 1, 90) for start in range(0, 480, 30)
        ),
    )

    plan = generate_contextual_plan(
        MelodyRequest(120, "C", "major", 1, 7), reference
    )

    assert len(plan.notes) == 8
    assert plan.report.warnings == (
        "Contextual density exceeded the monophonic eighth-note grid and was capped.",
    )


@pytest.mark.parametrize(
    "notes",
    [(), (NoteEvent(60, 0, 480, 90, mute=True),)],
)
def test_contextual_generation_requires_sounding_reference(notes):
    reference = EditableMidiClip(length_ticks=480, notes=notes)

    with pytest.raises(ValueError, match="sounding note"):
        generate_contextual_plan(
            MelodyRequest(120, "C", "major", 1, 1), reference
        )
