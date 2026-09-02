import pytest

from midi_generator.analysis import (
    analyze_clip,
    bass_line_pitches,
    rank_scale_candidates,
)
from midi_generator.domain import NoteEvent
from midi_generator.domain.music_theory import SCALE_INTERVALS
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
    assert profile.melodic_interval_count == 1
    assert profile.ascending_motion_count == 1
    assert profile.descending_motion_count == 0
    assert profile.repeated_motion_count == 0
    assert profile.mean_absolute_interval_semitones == 3.0
    assert profile.largest_interval_semitones == 3
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
    assert profile.melodic_interval_count == 0
    assert profile.ascending_motion_count == 0
    assert profile.descending_motion_count == 0
    assert profile.repeated_motion_count == 0
    assert profile.mean_absolute_interval_semitones is None
    assert profile.largest_interval_semitones is None
    assert profile.pitch_class_histogram == (0,) * 12
    assert profile.scale_candidates == ()


def test_melodic_motion_uses_highest_sounding_pitch_at_each_onset():
    clip = EditableMidiClip(
        length_ticks=1200,
        notes=(
            NoteEvent(60, 0, 240, 90),
            NoteEvent(67, 0, 240, 90),
            NoteEvent(65, 240, 240, 90),
            NoteEvent(65, 480, 240, 90),
            NoteEvent(72, 720, 240, 90),
            NoteEvent(84, 960, 240, 90, mute=True),
        ),
    )

    profile = analyze_clip(clip)

    assert profile.melodic_interval_count == 3
    assert profile.ascending_motion_count == 1
    assert profile.descending_motion_count == 1
    assert profile.repeated_motion_count == 1
    assert profile.mean_absolute_interval_semitones == 3.0
    assert profile.largest_interval_semitones == 7


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

    # 12 roots x every scale in SCALE_INTERVALS.
    assert len(candidates) == 12 * len(SCALE_INTERVALS)
    # Coverage wins first: C major covers all eight notes and has the strongest
    # tonic evidence (two C's), so it ranks ahead of every relative mode.
    assert candidates[0].root_note == "C"
    assert candidates[0].scale == "major"
    assert candidates[0].matching_note_count == 8
    assert candidates[0].tonic_note_count == 2
    assert candidates[0].coverage == 1.0
    # The next candidate still covers everything but has weaker tonic evidence.
    assert candidates[1].matching_note_count == 8
    assert candidates[1].coverage == 1.0
    assert candidates[1].tonic_note_count == 1


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


def test_bass_line_reads_the_lowest_pitch_of_each_beat():
    clip = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 90),
            NoteEvent(62, 480, 480, 90),
            NoteEvent(64, 960, 480, 90),
            NoteEvent(65, 1440, 480, 90),
        ),
    )

    assert bass_line_pitches(clip) == (60, 62, 64, 65)


def test_bass_line_takes_the_lowest_of_overlapping_voices_per_segment():
    clip = EditableMidiClip(
        length_ticks=960,
        notes=(
            NoteEvent(67, 0, 960, 90),
            NoteEvent(60, 0, 480, 90),
            NoteEvent(72, 480, 480, 90),
        ),
    )

    assert bass_line_pitches(clip) == (60, 67)


def test_bass_line_reports_a_sustained_note_in_every_segment_it_crosses():
    clip = EditableMidiClip(
        length_ticks=1440,
        notes=(NoteEvent(48, 0, 1440, 90),),
    )

    assert bass_line_pitches(clip) == (48, 48, 48)


def test_bass_line_marks_a_silent_segment_as_none():
    clip = EditableMidiClip(
        length_ticks=1440,
        notes=(
            NoteEvent(50, 0, 480, 90),
            NoteEvent(53, 960, 480, 90),
        ),
    )

    assert bass_line_pitches(clip) == (50, None, 53)


def test_bass_line_groups_by_the_requested_segment_width():
    clip = EditableMidiClip(
        length_ticks=1920,
        notes=(
            NoteEvent(60, 0, 480, 90),
            NoteEvent(55, 480, 480, 90),
            NoteEvent(64, 960, 480, 90),
            NoteEvent(62, 1440, 480, 90),
        ),
    )

    assert bass_line_pitches(clip, segment_beats=2) == (55, 62)


def test_bass_line_keeps_a_short_trailing_segment():
    clip = EditableMidiClip(
        length_ticks=1200,
        notes=(
            NoteEvent(60, 0, 480, 90),
            NoteEvent(61, 480, 480, 90),
            NoteEvent(70, 960, 240, 90),
        ),
    )

    assert bass_line_pitches(clip) == (60, 61, 70)


def test_bass_line_spanning_segment_wider_than_clip_returns_one_entry():
    clip = EditableMidiClip(
        length_ticks=480,
        notes=(NoteEvent(59, 0, 480, 90),),
    )

    assert bass_line_pitches(clip, segment_beats=4) == (59,)


def test_bass_line_ignores_muted_notes():
    clip = EditableMidiClip(
        length_ticks=960,
        notes=(
            NoteEvent(40, 0, 960, 90, mute=True),
            NoteEvent(60, 0, 480, 90),
        ),
    )

    assert bass_line_pitches(clip) == (60, None)


def test_bass_line_of_a_clip_without_sounding_notes_is_all_none():
    empty = EditableMidiClip(length_ticks=1440, notes=())
    muted = EditableMidiClip(
        length_ticks=1440,
        notes=(NoteEvent(50, 0, 1440, 90, mute=True),),
    )

    assert bass_line_pitches(empty) == (None, None, None)
    assert bass_line_pitches(muted) == (None, None, None)


@pytest.mark.parametrize("segment_beats", [0, -1, True, 1.0, "1"])
def test_bass_line_rejects_a_non_positive_integer_segment(segment_beats):
    clip = EditableMidiClip(length_ticks=960, notes=(NoteEvent(60, 0, 480, 90),))

    with pytest.raises(ValueError, match="segment_beats"):
        bass_line_pitches(clip, segment_beats=segment_beats)


def test_bass_line_validates_the_clip_before_reading_it():
    invalid = EditableMidiClip(
        length_ticks=480,
        notes=(NoteEvent(60, 0, 960, 90),),
    )

    with pytest.raises(ValueError, match="beyond"):
        bass_line_pitches(invalid)
