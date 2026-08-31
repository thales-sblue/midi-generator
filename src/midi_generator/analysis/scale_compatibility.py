"""Deterministic compatibility ranking across every scale in SCALE_INTERVALS."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from midi_generator.domain.music_theory import (
    PITCH_CLASS_NAMES,
    SCALE_INTERVALS,
)
from midi_generator.transformations import EditableMidiClip


@dataclass(frozen=True)
class ScaleCandidate:
    """Objective evidence for one scale, without claiming key detection."""

    root_note: str
    scale: str
    matching_note_count: int
    tonic_note_count: int
    coverage: float


def rank_scale_candidates(clip: EditableMidiClip) -> tuple[ScaleCandidate, ...]:
    """Rank every scale in SCALE_INTERVALS over the 12 roots by note coverage
    and tonic evidence. The tie-break keeps SCALE_INTERVALS insertion order, so
    ``major`` and ``minor`` still outrank the other modes on equal evidence."""
    clip.validate()
    pitch_classes = tuple(note.pitch % 12 for note in clip.notes if not note.mute)
    if not pitch_classes:
        return ()

    candidates: list[tuple[int, int, int, int, ScaleCandidate]] = []
    for root_pitch_class, root_note in enumerate(PITCH_CLASS_NAMES):
        for mode_order, scale in enumerate(SCALE_INTERVALS):
            allowed = {
                (root_pitch_class + interval) % 12
                for interval in SCALE_INTERVALS[scale]
            }
            matching = sum(pitch_class in allowed for pitch_class in pitch_classes)
            tonic_count = pitch_classes.count(root_pitch_class)
            candidate = ScaleCandidate(
                root_note=root_note,
                scale=scale,
                matching_note_count=matching,
                tonic_note_count=tonic_count,
                coverage=_coverage(matching, len(pitch_classes)),
            )
            candidates.append(
                (-matching, -tonic_count, root_pitch_class, mode_order, candidate)
            )

    candidates.sort(key=lambda item: item[:4])
    return tuple(item[4] for item in candidates)


def _coverage(matching: int, total: int) -> float:
    value = Decimal(matching) / Decimal(total)
    return float(value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))
