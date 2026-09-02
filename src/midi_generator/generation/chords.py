"""Deterministic diatonic chord bed that follows a reference clip's foundation."""

from midi_generator.domain import (
    CompositionPlan,
    GenerationReport,
    MelodyRequest,
    NoteEvent,
    scale_pitches,
)
from midi_generator.transformations import EditableMidiClip
from midi_generator.validation.musical_validation import validate_plan

from .foundation import build_foundation_line, voice_windows
from .melody import TICKS_PER_BEAT

DEFAULT_CHORD_VELOCITY = 80
MIN_CHORD_SIZE = 2
MAX_CHORD_SIZE = 5
# A stacked third is the next-but-one degree of the scale, whatever the scale.
DEGREE_STEP = 2


def generate_chord_bed_plan(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    segment_beats: int = 1,
    velocity: int = DEFAULT_CHORD_VELOCITY,
    sustain: bool = False,
    octave: int | None = None,
    chord_size: int = 3,
) -> CompositionPlan:
    """Turn a reference clip's foundation into a diatonic chord bed.

    Every ``segment_beats``-beat window of ``reference`` contributes its lowest
    sounding pitch, snapped to the nearest pitch of ``request``'s scale (ties
    downward); that pitch becomes the bass of a close-position chord built by
    stacking scale thirds above it — ``chord_size`` degrees taken every other
    step of the scale, so a triad in a seven-note scale is the familiar 1-3-5
    and ``chord_size=4`` adds the diatonic seventh. Silent windows stay silent.
    The plan spans exactly the reference clip, so ``request.bars`` and
    ``request.time_signature`` must describe that same length.

    Because the chord is read off the scale rather than off a fixed interval
    table, its quality follows the degree the foundation landed on: a chord bed
    over a C-major foundation is major on I, minor on ii, and so on.

    With ``sustain=False`` (default) each sounding window gets its own chord, a
    comping pulse on the metric grid. With ``sustain=True`` consecutive windows
    that produce the *same* chord are tied into one held chord — every voice
    extends together — so the harmonic rhythm follows the reference instead of
    the window size. A silent window always ends a held chord.

    ``octave`` anchors the register exactly as in
    :func:`~midi_generator.generation.bass_line.generate_bass_line_plan`: the
    lowest voice of the whole bed lands in that MIDI octave under one shared
    whole-octave offset, so the voicing is untouched. It is an error when a
    chord would then need a note above MIDI 127.

    The generator is fully deterministic and draws no randomness;
    ``request.seed`` is carried through to the report and metadata for
    provenance continuity only. Choosing the key stays an explicit decision of
    the caller.
    """
    if (
        not isinstance(velocity, int)
        or isinstance(velocity, bool)
        or not 1 <= velocity <= 127
    ):
        raise ValueError("velocity must be an integer between 1 and 127.")
    if not isinstance(sustain, bool):
        raise ValueError("sustain must be a boolean.")
    if (
        not isinstance(chord_size, int)
        or isinstance(chord_size, bool)
        or not MIN_CHORD_SIZE <= chord_size <= MAX_CHORD_SIZE
    ):
        raise ValueError(
            "chord_size must be an integer between "
            f"{MIN_CHORD_SIZE} and {MAX_CHORD_SIZE}."
        )

    line = build_foundation_line(
        request, reference, segment_beats=segment_beats, octave=octave
    )
    ladder = scale_pitches(request.root_note, request.scale)
    voiced = voice_windows(
        line,
        lambda bass: _stacked_thirds(bass, ladder, chord_size),
        sustain=sustain,
    )

    notes = tuple(
        NoteEvent(pitch=pitch, start=start, duration=end - start, velocity=velocity)
        for chord, start, end in voiced
        for pitch in chord
    )

    report = GenerationReport(
        note_count=len(notes),
        pause_count=len(line.pitches) - line.sounding_count,
        duration_ticks=line.total_ticks,
        scale=request.scale.lower(),
        seed=request.seed,
    )
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=notes,
        total_duration_ticks=line.total_ticks,
        report=report,
        metadata={
            "time_signature": str(request.time_signature),
            "ticks_per_beat": TICKS_PER_BEAT,
            "generation_mode": "chord_bed",
            "reference_length_ticks": reference.length_ticks,
            "segment_beats": segment_beats,
            "segment_count": len(line.pitches),
            "sounding_segment_count": line.sounding_count,
            "silent_segment_count": len(line.pitches) - line.sounding_count,
            "foundation_source": "analysis.bass_line_pitches",
            "pitch_mapping": "nearest_scale_pitch_ties_down",
            "voicing": "stacked_scale_thirds",
            "chord_size": chord_size,
            "chord_count": len(voiced),
            "note_grouping": "sustained" if sustain else "per_window",
            "target_octave": octave,
            "octave_offset_semitones": line.octave_offset,
            "velocity": velocity,
        },
    )
    validate_plan(plan)
    return plan


def _stacked_thirds(
    bass: int, ladder: tuple[int, ...], chord_size: int
) -> tuple[int, ...]:
    """Close-position chord of ``chord_size`` scale degrees stacked above ``bass``.

    ``ladder`` is every MIDI pitch of the scale, ascending, so taking every
    other entry from the bass upward stacks scale thirds without a chord table.
    """
    degree = ladder.index(bass)
    top = degree + DEGREE_STEP * (chord_size - 1)
    if top >= len(ladder):
        raise ValueError(
            f"A {chord_size}-note chord stacked on MIDI {bass} does not fit "
            "without a note exceeding MIDI 127."
        )
    return tuple(ladder[degree + DEGREE_STEP * step] for step in range(chord_size))
