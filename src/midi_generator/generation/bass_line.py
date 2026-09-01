"""Deterministic bass line that follows a reference clip's harmonic foundation."""

from midi_generator.analysis import bass_line_pitches
from midi_generator.domain import (
    CompositionPlan,
    GenerationReport,
    MelodyRequest,
    NoteEvent,
    nearest_scale_pitch,
    scale_pitch_classes,
)
from midi_generator.domain.music_theory import ROOT_NOTES, SCALE_INTERVALS
from midi_generator.transformations import EditableMidiClip
from midi_generator.validation.musical_validation import validate_plan

from .melody import TICKS_PER_BEAT

DEFAULT_BASS_VELOCITY = 96


def generate_bass_line_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    segment_beats: int = 1,
    velocity: int = DEFAULT_BASS_VELOCITY,
) -> CompositionPlan:
    """Turn a reference clip's bass line into a diatonic monophonic bass plan.

    ``analysis.bass_line_pitches`` reads the lowest sounding pitch of every
    ``segment_beats``-beat window (quarter-note beats) of ``reference``. Each
    such foundation pitch becomes one bass note snapped to the nearest pitch of
    ``request``'s scale, ties downward; silent windows stay silent. The plan
    spans exactly the reference clip, so ``request.bars`` and
    ``request.time_signature`` must describe that same length.

    The generator is fully deterministic and draws no randomness; ``request.seed``
    is carried through to the report and metadata for provenance continuity only.
    Choosing the key stays an explicit decision of the caller, which may feed it
    the scale candidates returned by :func:`analyze_clip` without turning an
    ambiguous compatibility into an automatic verdict.
    """
    request.validate()
    if request.root_note.upper() not in ROOT_NOTES:
        raise ValueError("Root note must be one of C, C#, Db, D, etc.")
    if request.scale.lower() not in SCALE_INTERVALS:
        raise ValueError(f"Scale must be one of: {', '.join(SCALE_INTERVALS)}.")
    if (
        not isinstance(velocity, int)
        or isinstance(velocity, bool)
        or not 1 <= velocity <= 127
    ):
        raise ValueError("velocity must be an integer between 1 and 127.")
    reference.validate()

    total_ticks = request.bars * request.time_signature.bar_ticks(TICKS_PER_BEAT)
    if total_ticks != reference.length_ticks:
        raise ValueError(
            "Bass-line generation requires the request length to match the "
            f"reference clip length ({reference.length_ticks} ticks), got "
            f"{total_ticks}."
        )
    if all(note.mute for note in reference.notes):
        raise ValueError("Reference clip must contain at least one sounding note.")

    foundation = bass_line_pitches(reference, segment_beats=segment_beats)
    pitch_classes = scale_pitch_classes(request.root_note, request.scale)
    segment_ticks = segment_beats * reference.ticks_per_beat

    notes: list[NoteEvent] = []
    for index, pitch in enumerate(foundation):
        if pitch is None:
            continue
        start = index * segment_ticks
        end = min(start + segment_ticks, total_ticks)
        notes.append(
            NoteEvent(
                pitch=nearest_scale_pitch(pitch, pitch_classes),
                start=start,
                duration=end - start,
                velocity=velocity,
            )
        )
    note_events = tuple(notes)

    sounding_segments = sum(pitch is not None for pitch in foundation)
    report = GenerationReport(
        note_count=len(note_events),
        pause_count=len(foundation) - sounding_segments,
        duration_ticks=total_ticks,
        scale=request.scale.lower(),
        seed=request.seed,
    )
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=note_events,
        total_duration_ticks=total_ticks,
        report=report,
        metadata={
            "time_signature": str(request.time_signature),
            "ticks_per_beat": TICKS_PER_BEAT,
            "generation_mode": "bass_line",
            "reference_length_ticks": reference.length_ticks,
            "segment_beats": segment_beats,
            "segment_count": len(foundation),
            "sounding_segment_count": sounding_segments,
            "silent_segment_count": len(foundation) - sounding_segments,
            "foundation_source": "analysis.bass_line_pitches",
            "pitch_mapping": "nearest_scale_pitch_ties_down",
            "velocity": velocity,
        },
    )
    validate_plan(plan)
    return plan
