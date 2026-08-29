import pytest

from midi_generator.analysis import analyze_clip, rank_scale_candidates
from midi_generator.domain import NoteEvent
from midi_generator.transformations import EditableMidiClip


def test_clip_profile_measures_sounding_musical_content():
    clip = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 40),
            NoteEvent(64, 0, 960, 80),
            NoteEvent(67, 480, 480, 100),
            NoteEvent(72, 960, 480, 127, mute=True),
        ),
    )

    profile = analyze_clip(clip)

    assert profile.clip_length_ticks == 1920
    assert profile.ticks_per_beat == 480
    assert profile.total_note_count == 4
    assert profile.sounding_note_count == 3
    assert profile.muted_note_count == 1
    assert profile.onset_count == 2
    assert profile.lowest_pitch == 60
    assert profile.highest_pitch == 67
    assert profile.pitch_range_semitones == 7
    assert profile.mean_velocity == 73.33
    assert profile.mean_duration_beats == 1.333
    assert profile.note_density_per_beat == 0.75
    assert profile.onset_density_per_beat == 0.5
    assert profile.max_polyphony == 2
    assert profile.pitch_class_histogram == (
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
    )


def test_empty_clip_has_explicit_zero_and_unknown_measurements():
    profile = analyze_clip(EditableMidiClip(length_ticks=960, notes=()))

    assert profile.total_note_count == 0
    assert profile.sounding_note_count == 0
    assert profile.onset_count == 0
    assert profile.lowest_pitch is None
    assert profile.highest_pitch is None
    assert profile.pitch_range_semitones is None
    assert profile.mean_velocity is None
    assert profile.mean_duration_beats is None
    assert profile.note_density_per_beat == 0.0
    assert profile.onset_density_per_beat == 0.0
    assert profile.max_polyphony == 0
    assert profile.pitch_class_histogram == (0,) * 12
    assert profile.scale_candidates == ()


def test_all_muted_notes_are_counted_but_excluded_from_musical_metrics():
    clip = EditableMidiClip(
        length_ticks=960,
        notes=(NoteEvent(61, 0, 480, 90, mute=True),),
    )

    profile = analyze_clip(clip)

    assert profile.total_note_count == 1
    assert profile.sounding_note_count == 0
    assert profile.muted_note_count == 1
    assert profile.pitch_class_histogram == (0,) * 12


def test_analysis_validates_clip_before_measuring():
    invalid = EditableMidiClip(
        length_ticks=480,
        notes=(NoteEvent(60, 0, 960, 90),),
    )

    with pytest.raises(ValueError, match="beyond"):
        analyze_clip(invalid)


def test_scale_candidates_rank_coverage_then_tonic_evidence():
    clip = EditableMidiClip(
        length_ticks=3840,
        notes=tuple(
            NoteEvent(pitch, index * 240, 240, 90)
            for index, pitch in enumerate((60, 60, 62, 64, 65, 67, 69, 71))
        ),
    )

    candidates = rank_scale_candidates(clip)

    assert len(candidates) == 24
    assert candidates[0].root_note == "C"
    assert candidates[0].scale == "major"
    assert candidates[0].matching_note_count == 8
    assert candidates[0].tonic_note_count == 2
    assert candidates[0].coverage == 1.0
    assert candidates[1].root_note == "A"
    assert candidates[1].scale == "minor"
    assert candidates[1].matching_note_count == 8
    assert candidates[1].coverage == 1.0


def test_scale_ranking_is_deterministic_and_ignores_muted_notes():
    clip = EditableMidiClip(
        length_ticks=960,
        notes=(
            NoteEvent(60, 0, 240, 90),
            NoteEvent(64, 240, 240, 90),
            NoteEvent(66, 480, 240, 90, mute=True),
        ),
    )

    first = rank_scale_candidates(clip)
    second = rank_scale_candidates(clip)

    assert first == second
    assert first[0].root_note == "C"
    assert first[0].scale == "major"
    assert first[0].coverage == 1.0
