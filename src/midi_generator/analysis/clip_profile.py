"""Objective musical profile of an editable MIDI clip."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from midi_generator.domain import NoteEvent
from midi_generator.transformations import EditableMidiClip


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
    pitch_class_histogram: tuple[int, ...]


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
        pitch_class_histogram=tuple(histogram),
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


def _rounded_ratio(numerator: int, denominator: int, digits: int) -> float:
    quantum = Decimal(1).scaleb(-digits)
    value = Decimal(numerator) / Decimal(denominator)
    return float(value.quantize(quantum, rounding=ROUND_HALF_UP))
