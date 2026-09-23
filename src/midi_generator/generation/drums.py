"""Deterministic drum patterns that follow a reference clip's musical context.

This module hosts the role-aware percussion generators. The first one,
:func:`generate_kick_plan`, places a kick relative to a reference clip. By
default it doubles every distinct onset of the reference, so the kick tracks
whatever rhythm is already playing; two ``placement`` modes swap that for a
fixed grid derived from the reference's length and metre (``downbeat_only``,
``four_on_floor``, ``odd_beats``). :func:`generate_snare_plan` places a snare
on the backbeat and :func:`generate_hihat_plan` a closed hi-hat on a steady
subdivision of the beat, metric grids derived the same way. Unlike the bass line and chord
bed, a drum voice is unpitched, so neither goes through ``generation.foundation``
and both ignore the request's key.
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
PLACEMENT_MODES = ("per_onset", "downbeat_only", "four_on_floor", "odd_beats")
DEFAULT_KICK_PLACEMENT = "per_onset"

# General MIDI acoustic snare.
SNARE_PITCH = 38
DEFAULT_SNARE_VELOCITY = 100
SNARE_DURATION_TICKS = 240

# General MIDI closed hi-hat.
HIHAT_PITCH = 42
DEFAULT_HIHAT_VELOCITY = 80
# Hits per quarter-note beat: 1 = quarters, 2 = eighths, 4 = sixteenths.
HIHAT_SUBDIVISIONS = (1, 2, 4)
DEFAULT_HIHAT_SUBDIVISION = 2
HIHAT_DURATION_TICKS = 120


def generate_kick_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    velocity: int = DEFAULT_KICK_VELOCITY,
    placement: str = DEFAULT_KICK_PLACEMENT,
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
    - ``"odd_beats"``: one kick on the 1st, 3rd, 5th... beat of every bar
      (beats 1 and 3 in 4/4), the complement of the snare's backbeat. The
      reference's own onsets are not read.

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
    elif placement == "four_on_floor":
        starts = list(range(0, total_ticks, TICKS_PER_BEAT))
    else:  # odd_beats: the 1st, 3rd, 5th... beat of every bar
        starts = [
            bar_start + offset
            for bar_start in range(0, total_ticks, bar_ticks)
            for offset in range(0, bar_ticks, 2 * TICKS_PER_BEAT)
        ]

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


def generate_snare_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    velocity: int = DEFAULT_SNARE_VELOCITY,
) -> CompositionPlan:
    """Place a snare (``SNARE_PITCH``, General MIDI acoustic snare) on the
    backbeat against ``reference``.

    The backbeat is a fixed metric grid, not a read of the reference's onsets:
    within every bar, one snare lands on every quarter note that is *not* the
    first of a pair, i.e. the 2nd, 4th, 6th, ... beat (beats 2 and 4 in 4/4).
    A bar with fewer than two beats never gets a snare, which the generator
    rejects up front. The plan spans exactly the reference clip, so
    ``request.bars`` and ``request.time_signature`` must describe that same
    length, and each snare is ``SNARE_DURATION_TICKS`` long, shortened when
    needed so it stops at the next snare or the clip end.

    A snare is unpitched, so ``request.root_note`` and ``request.scale`` are
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

    bar_ticks = request.time_signature.bar_ticks(TICKS_PER_BEAT)
    total_ticks = request.bars * bar_ticks
    if total_ticks != reference.length_ticks:
        raise ValueError(
            "Following a reference clip requires the request length to match "
            f"the reference clip length ({reference.length_ticks} ticks), got "
            f"{total_ticks}."
        )
    if bar_ticks < 2 * TICKS_PER_BEAT:
        raise ValueError(
            "Backbeat placement requires at least two beats per bar; "
            f"{request.time_signature} has too few."
        )

    starts = [
        bar_start + offset
        for bar_start in range(0, total_ticks, bar_ticks)
        for offset in range(TICKS_PER_BEAT, bar_ticks, 2 * TICKS_PER_BEAT)
    ]

    boundaries = [*starts[1:], total_ticks]
    notes = tuple(
        NoteEvent(
            pitch=SNARE_PITCH,
            start=start,
            duration=min(SNARE_DURATION_TICKS, boundary - start),
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
            "generation_mode": "snare",
            "placement": "backbeat",
            "reference_length_ticks": reference.length_ticks,
            "snare_count": len(notes),
            "snare_pitch": SNARE_PITCH,
            "velocity": velocity,
        },
    )
    validate_plan(plan)
    return plan


def generate_hihat_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    subdivision: int = DEFAULT_HIHAT_SUBDIVISION,
    velocity: int = DEFAULT_HIHAT_VELOCITY,
) -> CompositionPlan:
    """Play a closed hi-hat (``HIHAT_PITCH``, General MIDI) on a steady grid
    against ``reference``.

    ``subdivision`` hits land on every quarter-note beat, evenly spaced: ``1``
    for quarters, ``2`` (default) for eighths, ``4`` for sixteenths. Like the
    snare's backbeat, the grid comes only from the reference's length and
    metre, never from its onsets, so a silent reference is accepted. The plan
    spans exactly the reference clip, so ``request.bars`` and
    ``request.time_signature`` must describe that same length. Each hit is
    ``HIHAT_DURATION_TICKS`` long, shortened when needed so it stops at the
    next hit or the clip end.

    A hi-hat is unpitched, so ``request.root_note`` and ``request.scale`` are
    carried through for provenance continuity but play no musical role. The
    generator is fully deterministic and draws no randomness; ``request.seed``
    only reaches the report and metadata.
    """
    if subdivision not in HIHAT_SUBDIVISIONS or isinstance(subdivision, bool):
        raise ValueError(
            "subdivision must be one of "
            f"{', '.join(str(value) for value in HIHAT_SUBDIVISIONS)}; "
            f"got {subdivision!r}."
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

    step = TICKS_PER_BEAT // subdivision
    starts = list(range(0, total_ticks, step))
    boundaries = [*starts[1:], total_ticks]
    notes = tuple(
        NoteEvent(
            pitch=HIHAT_PITCH,
            start=start,
            duration=min(HIHAT_DURATION_TICKS, boundary - start),
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
            "generation_mode": "hihat",
            "subdivision": subdivision,
            "reference_length_ticks": reference.length_ticks,
            "hihat_count": len(notes),
            "hihat_pitch": HIHAT_PITCH,
            "velocity": velocity,
        },
    )
    validate_plan(plan)
    return plan
