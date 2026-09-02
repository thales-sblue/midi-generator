"""Deterministic drum patterns that follow a reference clip's musical context.

This module hosts the role-aware percussion generators. The first one,
:func:`generate_kick_plan`, places a kick relative to a reference clip. By
default it doubles every distinct onset of the reference, so the kick tracks
whatever rhythm is already playing; two ``placement`` modes swap that for a
fixed grid derived from the reference's length and metre (``downbeat_only``,
``four_on_floor``). Unlike the bass line and chord bed, a drum voice is
unpitched, so it does not go through ``generation.foundation`` and it ignores
the request's key.
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

# How the kick lines up with the reference clip.
PLACEMENT_MODES = ("per_onset", "downbeat_only", "four_on_floor")


def generate_kick_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    velocity: int = DEFAULT_KICK_VELOCITY,
    placement: str = "per_onset",
) -> CompositionPlan:
    """Place a kick (``KICK_PITCH``, General MIDI acoustic bass drum) against
    ``reference``.

    ``placement`` chooses where the kicks land. In every mode the plan spans
    exactly the reference clip, so ``request.bars`` and
    ``request.time_signature`` must describe that same length, and each kick is
    ``KICK_DURATION_TICKS`` long, shortened when needed so it stops at the next
    kick or the clip end.

    - ``"per_onset"`` (default): one kick on every distinct start tick of an
      unmuted note in ``reference``. A chord contributes one onset, muted notes
      contribute none; the reference must hold at least one sounding note.
    - ``"downbeat_only"``: one kick on the first beat of every bar, from the
      reference's length and metre. The reference's own onsets are not read.
    - ``"four_on_floor"``: one kick on every quarter note. The reference's own
      onsets are not read.

    A kick is unpitched, so ``request.root_note`` and ``request.scale`` are
    carried through for provenance continuity but play no musical role. The
    generator is fully deterministic and draws no randomness; ``request.seed``
    only reaches the report and metadata.
    """
    if placement not in PLACEMENT_MODES:
        raise ValueError(
            "placement must be one of "
            f"{', '.join(PLACEMENT_MODES)}; got {placement!r}."
        )
    if (
        not isinstance(velocity, int)
        or isinstance(velocity, bool)
        or not 1 <= velocity <= 127
    ):
        raise ValueError("velocity must be an integer between 1 and 127.")

    request.validate()
    reference.validate()

    bar_ticks = request.time_signature.bar_ticks(TICKS_PER_BEAT)
    total_ticks = request.bars * bar_ticks
    if total_ticks != reference.length_ticks:
        raise ValueError(
            "Following a reference clip requires the request length to match "
            f"the reference clip length ({reference.length_ticks} ticks), got "
            f"{total_ticks}."
        )

    onsets = sorted({note.start for note in reference.notes if not note.mute})

    if placement == "per_onset":
        if not onsets:
            raise ValueError(
                "Reference clip must contain at least one sounding note."
            )
        starts = onsets
    elif placement == "downbeat_only":
        starts = list(range(0, total_ticks, bar_ticks))
    else:  # four_on_floor: one kick per quarter note
        starts = list(range(0, total_ticks, TICKS_PER_BEAT))

    boundaries = [*starts[1:], total_ticks]
    notes = tuple(
        NoteEvent(
            pitch=KICK_PITCH,
            start=start,
            duration=min(KICK_DURATION_TICKS, boundary - start),
            velocity=velocity,
        )
        for start, boundary in zip(starts, boundaries)
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
            "placement": placement,
            "reference_length_ticks": reference.length_ticks,
            "onset_source": (
                "distinct sounding note starts"
                if placement == "per_onset"
                else f"{placement} grid"
            ),
            "onset_count": len(onsets),
            "kick_count": len(notes),
            "kick_pitch": KICK_PITCH,
            "velocity": velocity,
        },
    )
    validate_plan(plan)
    return plan
