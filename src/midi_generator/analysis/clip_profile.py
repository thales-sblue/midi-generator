"""Objective musical profile of an editable MIDI clip."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from midi_generator.domain import NoteEvent
from midi_generator.transformations import EditableMidiClip

from .scale_compatibility import ScaleCandidate, rank_scale_candidates


@dataclass(frozen=True)
class ClipProfile:
    """Deterministic summary that future musical decisions can build upon."""

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
    melodic_interval_count: int
    ascending_motion_count: int
    descending_motion_count: int
    repeated_motion_count: int
    mean_absolute_interval_semitones: float | None
    largest_interval_semitones: int | None
    pitch_class_histogram: tuple[int, ...]
    scale_candidates: tuple[ScaleCandidate, ...]


def analyze_clip(clip: EditableMidiClip) -> ClipProfile:
    """Measure the sounding content of a clip without changing it."""
    clip.validate()
    sounding = tuple(note for note in clip.notes if not note.mute)
    onsets = {note.start for note in sounding}
    pitches = tuple(note.pitch for note in sounding)
    velocities = tuple(note.velocity for note in sounding)
    durations = tuple(note.duration for note in sounding)

    histogram = [0] * 12
    for pitch in pitches:
        histogram[pitch % 12] += 1

    lowest_pitch = min(pitches) if pitches else None
    highest_pitch = max(pitches) if pitches else None
    sounding_count = len(sounding)
    melodic_intervals = top_line_intervals(sounding)
    melodic_interval_count = len(melodic_intervals)
    return ClipProfile(
        clip_length_ticks=clip.length_ticks,
        ticks_per_beat=clip.ticks_per_beat,
        total_note_count=len(clip.notes),
        sounding_note_count=sounding_count,
        muted_note_count=len(clip.notes) - sounding_count,
        onset_count=len(onsets),
        lowest_pitch=lowest_pitch,
        highest_pitch=highest_pitch,
        pitch_range_semitones=(
            highest_pitch - lowest_pitch if pitches else None
        ),
        mean_velocity=(
            _rounded_ratio(sum(velocities), sounding_count, 2)
            if sounding
            else None
        ),
        mean_duration_beats=(
            _rounded_ratio(
                sum(durations), sounding_count * clip.ticks_per_beat, 3
            )
            if sounding
            else None
        ),
        note_density_per_beat=_rounded_ratio(
            sounding_count * clip.ticks_per_beat, clip.length_ticks, 3
        ),
        onset_density_per_beat=_rounded_ratio(
            len(onsets) * clip.ticks_per_beat, clip.length_ticks, 3
        ),
        max_polyphony=_max_polyphony(sounding),
        melodic_interval_count=melodic_interval_count,
        ascending_motion_count=sum(interval > 0 for interval in melodic_intervals),
        descending_motion_count=sum(interval < 0 for interval in melodic_intervals),
        repeated_motion_count=sum(interval == 0 for interval in melodic_intervals),
        mean_absolute_interval_semitones=(
            _rounded_ratio(
                sum(abs(interval) for interval in melodic_intervals),
                melodic_interval_count,
                2,
            )
            if melodic_intervals
            else None
        ),
        largest_interval_semitones=(
            max(abs(interval) for interval in melodic_intervals)
            if melodic_intervals
            else None
        ),
        pitch_class_histogram=tuple(histogram),
        scale_candidates=rank_scale_candidates(clip),
    )


def _max_polyphony(notes: tuple[NoteEvent, ...]) -> int:
    deltas: dict[int, int] = {}
    for note in notes:
        deltas[note.start] = deltas.get(note.start, 0) + 1
        end = note.start + note.duration
        deltas[end] = deltas.get(end, 0) - 1

    active = 0
    maximum = 0
    for position in sorted(deltas):
        active += deltas[position]
        maximum = max(maximum, active)
    return maximum


def top_line_intervals(notes: tuple[NoteEvent, ...]) -> tuple[int, ...]:
    """Return intervals between the highest sounding pitches of successive onsets."""
    highest_pitch_by_onset: dict[int, int] = {}
    for note in notes:
        if note.mute:
            continue
        highest_pitch_by_onset[note.start] = max(
            note.pitch, highest_pitch_by_onset.get(note.start, note.pitch)
        )
    top_line = tuple(
        highest_pitch_by_onset[onset] for onset in sorted(highest_pitch_by_onset)
    )
    return tuple(
        following - current
        for current, following in zip(top_line, top_line[1:])
    )


def _rounded_ratio(numerator: int, denominator: int, digits: int) -> float:
    quantum = Decimal(1).scaleb(-digits)
    value = Decimal(numerator) / Decimal(denominator)
    return float(value.quantize(quantum, rounding=ROUND_HALF_UP))
