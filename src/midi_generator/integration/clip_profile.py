"""JSON-safe serialization for deterministic clip analysis."""

from typing import TypedDict

from midi_generator.analysis import ClipProfile


class ScaleCandidatePayload(TypedDict):
    root_note: str
    scale: str
    matching_note_count: int
    tonic_note_count: int
    coverage: float


class ClipProfilePayload(TypedDict):
    clip_length_ticks: int
    ticks_per_beat: int
    total_note_count: int
    sounding_note_count: int
    muted_note_count: int
    onset_count: int
    lowest_pitch: int | None
    highest_pitch: int | None
    pitch_range_semitones: int | None
    mean_velocity: float | None
    mean_duration_beats: float | None
    note_density_per_beat: float
    onset_density_per_beat: float
    max_polyphony: int
    pitch_class_histogram: list[int]
    scale_candidates: list[ScaleCandidatePayload]


def clip_profile_to_payload(profile: ClipProfile) -> ClipProfilePayload:
    """Convert an immutable profile into a JSON-safe integration value."""
    return ClipProfilePayload(
        clip_length_ticks=profile.clip_length_ticks,
        ticks_per_beat=profile.ticks_per_beat,
        total_note_count=profile.total_note_count,
        sounding_note_count=profile.sounding_note_count,
        muted_note_count=profile.muted_note_count,
        onset_count=profile.onset_count,
        lowest_pitch=profile.lowest_pitch,
        highest_pitch=profile.highest_pitch,
        pitch_range_semitones=profile.pitch_range_semitones,
        mean_velocity=profile.mean_velocity,
        mean_duration_beats=profile.mean_duration_beats,
        note_density_per_beat=profile.note_density_per_beat,
        onset_density_per_beat=profile.onset_density_per_beat,
        max_polyphony=profile.max_polyphony,
        pitch_class_histogram=list(profile.pitch_class_histogram),
        scale_candidates=[
            ScaleCandidatePayload(
                root_note=candidate.root_note,
                scale=candidate.scale,
                matching_note_count=candidate.matching_note_count,
                tonic_note_count=candidate.tonic_note_count,
                coverage=candidate.coverage,
            )
            for candidate in profile.scale_candidates
        ],
    )
