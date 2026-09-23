"""Bass and drums that accompany an analysed piece.

A :class:`MusicAnalysis` (from audio today, from MIDI later) is turned into the
two things the role-aware generators already take: a ``MelodyRequest`` that
carries tempo, key, metre and length, and a *harmonic reference clip* whose
notes are the detected chord roots, one per chord, placed on the analysis beat
grid. The bass line and drum voices are then produced by the existing
generators in ``bass_line.py`` and ``drums.py``; this module adds no second
bass or drum algorithm.

Plan tick 0 is the first downbeat of the analysis. To play a plan against the
source recording, export it with :func:`accompaniment_tempo_map`, which gives
every beat the duration it had in the recording.
"""

from dataclasses import dataclass, replace

from midi_generator.domain import (
    CompositionPlan,
    MelodyRequest,
    MidiTempoMap,
    MusicAnalysis,
    NoteEvent,
    scale_pitch_classes,
    tempo_map_for_grid,
)
from midi_generator.transformations import EditableMidiClip
from midi_generator.validation.musical_validation import validate_plan

from .bass_line import DEFAULT_BASS_VELOCITY, generate_bass_line_plan
from .drums import (
    DEFAULT_HIHAT_VELOCITY,
    DEFAULT_KICK_VELOCITY,
    DEFAULT_SNARE_VELOCITY,
    generate_hihat_plan,
    generate_kick_plan,
    generate_snare_plan,
)
from .melody import TICKS_PER_BEAT

# Chord roots are written from E1 up to D#2, the lowest octave of a
# four-string bass, so the reference already sits in a bass register.
BASS_ROOT_FLOOR = 28
_E_PITCH_CLASS = 4
_REFERENCE_VELOCITY = 100


@dataclass(frozen=True)
class DrumStyle:
    """How each drum voice is placed; the seed of a future style library."""

    name: str
    kick_placement: str
    hihat_subdivision: int
    kick_velocity: int = DEFAULT_KICK_VELOCITY
    snare_velocity: int = DEFAULT_SNARE_VELOCITY
    hihat_velocity: int = DEFAULT_HIHAT_VELOCITY


# Only a neutral backbeat for now. Genre styles (rock, grunge, punk...) are
# new entries here once they are specified and listened to.
DRUM_STYLES = {
    "basic": DrumStyle(name="basic", kick_placement="odd_beats", hihat_subdivision=2),
}
DEFAULT_DRUM_STYLE = "basic"


@dataclass(frozen=True)
class Accompaniment:
    """Bass and drum plans for an analysis, plus the map that aligns them."""

    bass: CompositionPlan
    drums: CompositionPlan
    tempo_map: MidiTempoMap


def analysis_request(analysis: MusicAnalysis, *, seed: int = 0) -> MelodyRequest:
    """The generation request an analysis implies.

    Tempo is rounded to a whole BPM (the plan's nominal tempo; exact beat
    timing travels in the tempo map), and the request spans every complete bar.
    """
    if analysis.bar_count < 1:
        raise ValueError("The analysis holds no complete bar to accompany.")
    request = MelodyRequest(
        bpm=min(max(round(analysis.tempo_bpm), 20), 400),
        root_note=analysis.key.root_note,
        scale=analysis.key.scale,
        bars=analysis.bar_count,
        seed=seed,
        time_signature=analysis.time_signature,
    )
    request.validate()
    return request


def harmonic_reference_clip(analysis: MusicAnalysis) -> EditableMidiClip:
    """Materialise the chord timeline as a clip the generators can follow.

    Every chord segment becomes one note on its root, between E1 and D#2,
    starting and ending on the nearest beat of the analysis grid and clipped
    to the complete bars. No-chord stretches stay silent.
    """
    grid = analysis.grid
    total_beats = analysis.bar_count * grid.beats_per_bar
    notes = []
    for segment in analysis.chords:
        if not segment.is_chord:
            continue
        start = min(max(round(grid.seconds_to_beat(segment.start_seconds)), 0), total_beats)
        end = min(max(round(grid.seconds_to_beat(segment.end_seconds)), 0), total_beats)
        if end <= start:
            continue
        pitch = BASS_ROOT_FLOOR + (segment.root_pitch_class - _E_PITCH_CLASS) % 12
        notes.append(
            NoteEvent(
                pitch=pitch,
                start=start * TICKS_PER_BEAT,
                duration=(end - start) * TICKS_PER_BEAT,
                velocity=_REFERENCE_VELOCITY,
            )
        )
    clip = EditableMidiClip(
        length_ticks=total_beats * TICKS_PER_BEAT, notes=tuple(notes)
    )
    clip.validate()
    return clip


def generate_bass_from_analysis(
    analysis: MusicAnalysis,
    *,
    seed: int = 0,
    sustain: bool = True,
    velocity: int = DEFAULT_BASS_VELOCITY,
) -> CompositionPlan:
    """A root-note bass line that follows the detected progression.

    Delegates to :func:`generate_bass_line_plan` over the harmonic reference
    clip, one window per beat. With ``sustain`` (default) a chord held for
    several beats becomes one held bass note; without it the bass pulses on
    every beat. Roots are snapped into the detected key like any other
    reference; a root that had to move is reported in the plan's warnings,
    because it means the chord and the key estimate disagree.
    """
    request = analysis_request(analysis, seed=seed)
    reference = harmonic_reference_clip(analysis)
    plan = generate_bass_line_plan(
        request, reference, segment_beats=1, velocity=velocity, sustain=sustain
    )

    key_classes = scale_pitch_classes(request.root_note, request.scale)
    outside = sorted(
        {
            segment.symbol
            for segment in analysis.chords
            if segment.is_chord and segment.root_pitch_class not in key_classes
        }
    )
    warnings = plan.report.warnings
    if outside:
        warnings += (
            f"Chord roots outside {analysis.key.name} were snapped into the key: "
            f"{', '.join(outside)}.",
        )
    return replace(
        plan,
        report=replace(plan.report, warnings=warnings),
        metadata={
            **plan.metadata,
            "harmony_source": "music_analysis",
            "analysis_source": analysis.source,
            "progression": " ".join(analysis.progression()),
        },
    )


def generate_drums_from_analysis(
    analysis: MusicAnalysis,
    *,
    style: str = DEFAULT_DRUM_STYLE,
    seed: int = 0,
) -> CompositionPlan:
    """Kick, snare and closed hi-hat on the analysis bar grid, as one plan.

    Each voice comes from its generator in ``drums.py`` with the placement the
    ``style`` names (``"basic"``: kick on beats 1 and 3, snare on 2 and 4,
    hi-hat on eighths in 4/4). The voices are merged in time order.
    """
    if style not in DRUM_STYLES:
        raise ValueError(
            f"style must be one of {', '.join(DRUM_STYLES)}; got {style!r}."
        )
    drum_style = DRUM_STYLES[style]
    request = analysis_request(analysis, seed=seed)
    reference = harmonic_reference_clip(analysis)

    kick = generate_kick_plan(
        request,
        reference,
        velocity=drum_style.kick_velocity,
        placement=drum_style.kick_placement,
    )
    snare = generate_snare_plan(request, reference, velocity=drum_style.snare_velocity)
    hihat = generate_hihat_plan(
        request,
        reference,
        subdivision=drum_style.hihat_subdivision,
        velocity=drum_style.hihat_velocity,
    )
    notes = tuple(
        sorted(
            (*kick.notes, *snare.notes, *hihat.notes),
            key=lambda note: (note.start, note.pitch),
        )
    )
    plan = CompositionPlan(
        request=request,
        seed=request.seed,
        notes=notes,
        total_duration_ticks=kick.total_duration_ticks,
        report=replace(kick.report, note_count=len(notes)),
        metadata={
            "time_signature": str(request.time_signature),
            "ticks_per_beat": TICKS_PER_BEAT,
            "generation_mode": "drum_kit",
            "style": drum_style.name,
            "kick_placement": drum_style.kick_placement,
            "hihat_subdivision": drum_style.hihat_subdivision,
            "kick_count": len(kick.notes),
            "snare_count": len(snare.notes),
            "hihat_count": len(hihat.notes),
            "analysis_source": analysis.source,
        },
    )
    validate_plan(plan)
    return plan


def accompaniment_tempo_map(analysis: MusicAnalysis) -> MidiTempoMap:
    """Tempo map that lays accompaniment plans onto the source recording."""
    return tempo_map_for_grid(
        analysis.grid, bars=analysis.bar_count, ticks_per_beat=TICKS_PER_BEAT
    )


def generate_accompaniment(
    analysis: MusicAnalysis,
    *,
    style: str = DEFAULT_DRUM_STYLE,
    seed: int = 0,
    sustain_bass: bool = True,
) -> Accompaniment:
    """Bass and drums for ``analysis`` together with their alignment map."""
    return Accompaniment(
        bass=generate_bass_from_analysis(analysis, seed=seed, sustain=sustain_bass),
        drums=generate_drums_from_analysis(analysis, style=style, seed=seed),
        tempo_map=accompaniment_tempo_map(analysis),
    )
