"""Objective, deterministic proxy metrics for ranking candidate plans.

These metrics are transparent measurements, not a verdict on musical quality.
Like the scale-compatibility ranking, the harness surfaces objective evidence so
a human (or the listening gate) can choose; it never turns an ambiguous score
into an automatic winner. The v0 aggregate is a plain equal-weighted mean of the
four sub-metrics and is expected to evolve.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import log2

from midi_generator.analysis import ClipProfile, analyze_clip
from midi_generator.domain import CompositionPlan
from midi_generator.transformations import EditableMidiClip

_QUANTUM = Decimal("0.001")


@dataclass(frozen=True)
class CandidateScore:
    """Objective proxy metrics for one candidate, each in ``0.0..1.0``."""

    motion_entropy: float
    pitch_class_diversity: float
    rhythmic_activity: float
    leap_control: float
    aggregate: float


def plan_to_clip(plan: CompositionPlan) -> EditableMidiClip:
    """Wrap a finished plan as an editable clip for analysis."""
    return EditableMidiClip(
        length_ticks=plan.total_duration_ticks, notes=plan.notes
    )


def score_plan(plan: CompositionPlan) -> CandidateScore:
    """Score a composition plan through the shared objective clip profile."""
    return score_profile(analyze_clip(plan_to_clip(plan)))


def score_profile(profile: ClipProfile) -> CandidateScore:
    """Derive the proxy metrics from an already computed clip profile."""
    motion_entropy = _normalised_entropy(
        (
            profile.ascending_motion_count,
            profile.descending_motion_count,
            profile.repeated_motion_count,
        )
    )
    distinct_pitch_classes = sum(
        1 for count in profile.pitch_class_histogram if count
    )
    pitch_class_diversity = min(1.0, distinct_pitch_classes / 7)

    step_ticks = profile.ticks_per_beat // 2
    step_count = profile.clip_length_ticks // step_ticks
    rhythmic_activity = (
        profile.onset_count / step_count if step_count else 0.0
    )
    rhythmic_activity = min(1.0, rhythmic_activity)

    largest = profile.largest_interval_semitones
    leap_control = (
        1.0 if largest is None else max(0.0, 1.0 - min(1.0, largest / 12))
    )

    components = (
        _quantise(motion_entropy),
        _quantise(pitch_class_diversity),
        _quantise(rhythmic_activity),
        _quantise(leap_control),
    )
    aggregate = _quantise(sum(components) / len(components))
    return CandidateScore(*components, aggregate=aggregate)


def _normalised_entropy(counts: tuple[int, ...]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if not count:
            continue
        probability = count / total
        entropy -= probability * log2(probability)
    return entropy / log2(len(counts))


def _quantise(value: float) -> float:
    return float(Decimal(value).quantize(_QUANTUM, rounding=ROUND_HALF_UP))
