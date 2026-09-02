"""Deterministic bass line that follows a reference clip's harmonic foundation."""

from midi_generator.domain import (
    CompositionPlan,
    GenerationReport,
    MelodyRequest,
    NoteEvent,
)
from midi_generator.transformations import EditableMidiClip
from midi_generator.validation.musical_validation import validate_plan

from .foundation import build_foundation_line, voice_windows
from .melody import TICKS_PER_BEAT

DEFAULT_BASS_VELOCITY = 96


def generate_bass_line_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    segment_beats: int = 1,
    velocity: int = DEFAULT_BASS_VELOCITY,
    sustain: bool = False,
    octave: int | None = None,
) -> CompositionPlan:
    """Turn a reference clip's bass line into a diatonic monophonic bass plan.

    ``generation.foundation.build_foundation_line`` reads the lowest sounding
    pitch of every ``segment_beats``-beat window (quarter-note beats) of
    ``reference`` and snaps it to the nearest pitch of ``request``'s scale, ties
    downward. Each such foundation pitch becomes one bass note; silent windows
    stay silent. The plan spans exactly the reference clip, so ``request.bars``
    and ``request.time_signature`` must describe that same length.

    With ``sustain=False`` (default) every sounding window yields its own note,
    a repeated-note pulse that tracks the metric grid. With ``sustain=True``
    consecutive windows that snap to the *same* scale pitch are tied into a
    single held note, so a static foundation reads as one sustained bass note
    and the harmonic rhythm of the output follows the reference rather than the
    window size. A silent window always ends a held note.

    ``octave`` is ``None`` by default, which keeps whatever register the
    reference's lowest notes sat in. Given an integer MIDI octave (``C-1`` is
    octave ``-1``, middle C is octave ``4``), the whole line is transposed by a
    single whole-octave offset so its lowest note lands in that octave; the
    contour and every interval are preserved because one offset applies to all
    notes. It is an error if that offset would push any note above MIDI 127.

    The generator is fully deterministic and draws no randomness; ``request.seed``
    is carried through to the report and metadata for provenance continuity only.
    Choosing the key stays an explicit decision of the caller, which may feed it
    the scale candidates returned by :func:`analyze_clip` without turning an
    ambiguous compatibility into an automatic verdict.
    """
    if (
        not isinstance(velocity, int)
        or isinstance(velocity, bool)
        or not 1 <= velocity <= 127
    ):
        raise ValueError("velocity must be an integer between 1 and 127.")
    if not isinstance(sustain, bool):
        raise ValueError("sustain must be a boolean.")

    line = build_foundation_line(
        request, reference, segment_beats=segment_beats, octave=octave
    )

    note_events = tuple(
        NoteEvent(pitch=pitch, start=start, duration=end - start, velocity=velocity)
        for pitches, start, end in voice_windows(
            line, lambda pitch: (pitch,), sustain=sustain
        )
        for pitch in pitches
    )

    report = GenerationReport(
        note_count=len(note_events),
        pause_count=len(line.pitches) - line.sounding_count,
        duration_ticks=line.total_ticks,
        scale=request.scale.lower(),
        seed=request.seed,
    )
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=note_events,
        total_duration_ticks=line.total_ticks,
        report=report,
        metadata={
            "time_signature": str(request.time_signature),
            "ticks_per_beat": TICKS_PER_BEAT,
            "generation_mode": "bass_line",
            "reference_length_ticks": reference.length_ticks,
            "segment_beats": segment_beats,
            "segment_count": len(line.pitches),
            "sounding_segment_count": line.sounding_count,
            "silent_segment_count": len(line.pitches) - line.sounding_count,
            "foundation_source": "analysis.bass_line_pitches",
            "pitch_mapping": "nearest_scale_pitch_ties_down",
            "note_grouping": "sustained" if sustain else "per_window",
            "target_octave": octave,
            "octave_offset_semitones": line.octave_offset,
            "velocity": velocity,
        },
    )
    validate_plan(plan)
    return plan
