"""Deterministic drum patterns that follow a reference clip's musical context.

This module hosts the role-aware percussion generators. The first one,
:func:`generate_kick_plan`, places a kick on every distinct onset of a
reference clip, so the kick doubles whatever rhythm is already playing.
Unlike the bass line and chord bed, a drum voice is unpitched, so it does not
go through ``generation.foundation`` and it ignores the request's key.
"""

from midi_generator.domain import (
    CompositionPlan,
    GenerationReport,
    MelodyRequest,
    NoteEvent,
)
from midi_generator.transformations import EditableMidiClip
from midi_generator.validation.musical_validation import validate_plan

from .melody import TICKS_PER_BEAT

# General MIDI acoustic bass drum.
KICK_PITCH = 36
DEFAULT_KICK_VELOCITY = 100
# A short trigger length; clamped so it never crosses the next onset or the
# clip end.
KICK_DURATION_TICKS = 240


def generate_kick_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    velocity: int = DEFAULT_KICK_VELOCITY,
) -> CompositionPlan:
    """Place one kick on each distinct sounding onset of ``reference``.

    Every distinct start tick of an unmuted note in ``reference`` becomes a
    single kick (``KICK_PITCH``, General MIDI acoustic bass drum). A chord
    contributes one onset, muted notes contribute none. Each kick is
    ``KICK_DURATION_TICKS`` long, shortened when needed so it stops at the next
    onset or the clip end. The plan spans exactly the reference clip, so
    ``request.bars`` and ``request.time_signature`` must describe that same
    length.

    A kick is unpitched, so ``request.root_note`` and ``request.scale`` are
    carried through for provenance continuity but play no musical role. The
    generator is fully deterministic and draws no randomness; ``request.seed``
    only reaches the report and metadata.
    """
    if (
        not isinstance(velocity, int)
        or isinstance(velocity, bool)
        or not 1 <= velocity <= 127
    ):
        raise ValueError("velocity must be an integer between 1 and 127.")

    request.validate()
    reference.validate()

    total_ticks = request.bars * request.time_signature.bar_ticks(TICKS_PER_BEAT)
    if total_ticks != reference.length_ticks:
        raise ValueError(
            "Following a reference clip requires the request length to match "
            f"the reference clip length ({reference.length_ticks} ticks), got "
            f"{total_ticks}."
        )

    onsets = sorted({note.start for note in reference.notes if not note.mute})
    if not onsets:
        raise ValueError("Reference clip must contain at least one sounding note.")

    boundaries = [*onsets[1:], total_ticks]
    notes = tuple(
        NoteEvent(
            pitch=KICK_PITCH,
            start=onset,
            duration=min(KICK_DURATION_TICKS, boundary - onset),
            velocity=velocity,
        )
        for onset, boundary in zip(onsets, boundaries)
    )

    report = GenerationReport(
        note_count=len(notes),
        pause_count=0,
        duration_ticks=total_ticks,
        scale=request.scale.lower(),
        seed=request.seed,
    )
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=notes,
        total_duration_ticks=total_ticks,
        report=report,
        metadata={
            "time_signature": str(request.time_signature),
            "ticks_per_beat": TICKS_PER_BEAT,
            "generation_mode": "kick",
            "reference_length_ticks": reference.length_ticks,
            "onset_source": "distinct sounding note starts",
            "onset_count": len(notes),
            "kick_pitch": KICK_PITCH,
            "velocity": velocity,
        },
    )
    validate_plan(plan)
    return plan
