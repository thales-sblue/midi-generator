"""Minimal structural validation for composition plans."""

from midi_generator.domain.composition_plan import CompositionPlan


def validate_plan(plan: CompositionPlan) -> None:
    for note in plan.notes:
        if not 0 <= note.pitch <= 127:
            raise ValueError("Note pitch must be between 0 and 127.")
        if note.start < 0 or note.duration <= 0:
            raise ValueError("Note timing must be positive.")
        if note.start + note.duration > plan.total_duration_ticks:
            raise ValueError("Note extends beyond plan duration.")
        if not 1 <= note.velocity <= 127:
            raise ValueError("Velocity must be between 1 and 127.")
