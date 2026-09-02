"""High-level orchestration for safe Ableton clip transformations and generation.

Every function here only sequences reads, preflight, a fingerprint-protected
duplication and a copy-only replace. The musical algorithms live in
``transformations/`` and ``generation/`` and are reached through callables.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from midi_generator.ableton import AbletonClient
from midi_generator.domain import CompositionPlan, MelodyRequest
from midi_generator.generation import (
    generate_bass_line_plan,
    generate_chord_bed_plan,
    generate_contextual_plan,
)
from midi_generator.generation.bass_line import DEFAULT_BASS_VELOCITY
from midi_generator.generation.chords import DEFAULT_CHORD_VELOCITY
from midi_generator.generation.melody import BEATS_PER_BAR
from midi_generator.integration import (
    ableton_snapshot_to_clip,
    beats_to_ticks,
    clip_notes_to_ableton,
)
from midi_generator.transformations import (
    EditableMidiClip,
    constrain_to_scale,
    harmonize_diatonic,
    humanize,
    invert,
    legato,
    quantize,
    retrograde,
    staccato,
    transpose,
    transpose_diatonic,
    velocity_ramp,
)

TRANSFORMS = {
    "transpose",
    "invert",
    "retrograde",
    "legato",
    "staccato",
    "quantize",
    "humanize",
    "constrain_to_scale",
    "transpose_diatonic",
    "harmonize_diatonic",
    "velocity_ramp",
}


class TransformedClipResult(TypedDict):
    transformed: bool
    transform: str
    source_track_index: int
    source_scene_index: int
    target_track_index: int
    target_scene_index: int
    clip_length_beats: float
    note_count: int
    source_clip_fingerprint: str
    target_clip_fingerprint: str


class ContextualVariationResult(TypedDict):
    contextualized: bool
    source_track_index: int
    source_scene_index: int
    target_track_index: int
    target_scene_index: int
    clip_length_beats: float
    note_count: int
    source_clip_fingerprint: str
    target_clip_fingerprint: str
    bpm: int
    root_note: str
    scale: str
    seed: int


class BassLineClipResult(TypedDict):
    generated: bool
    role: str
    source_track_index: int
    source_scene_index: int
    target_track_index: int
    target_scene_index: int
    clip_length_beats: float
    note_count: int
    source_clip_fingerprint: str
    target_clip_fingerprint: str
    bpm: int
    root_note: str
    scale: str
    seed: int
    bars: int
    segment_beats: int
    velocity: int
    sustain: bool
    octave: int | None
    note_grouping: str
    octave_offset_semitones: int


class ChordBedClipResult(TypedDict):
    generated: bool
    role: str
    source_track_index: int
    source_scene_index: int
    target_track_index: int
    target_scene_index: int
    clip_length_beats: float
    note_count: int
    source_clip_fingerprint: str
    target_clip_fingerprint: str
    bpm: int
    root_note: str
    scale: str
    seed: int
    bars: int
    segment_beats: int
    velocity: int
    sustain: bool
    octave: int | None
    chord_size: int
    chord_count: int
    voicing: str
    note_grouping: str
    octave_offset_semitones: int


@dataclass(frozen=True)
class _GeneratedCopy:
    """Outcome of the shared read/preflight/duplicate/replace pipeline."""

    source_fingerprint: str
    bars: int
    plan: CompositionPlan
    replacement: dict[str, Any]


def _generate_into_protected_copy(
    client: AbletonClient,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    build_plan: Callable[[MelodyRequest, EditableMidiClip], CompositionPlan],
    *,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
) -> _GeneratedCopy:
    """Read the source, preflight generation, then write only a protected copy.

    ``build_plan`` turns the source clip and a length-matched request into a
    :class:`CompositionPlan`; every musical decision (and its validation) lives
    inside that callable, never here. The source snapshot is read once, the plan
    is generated once before any Ableton mutation, the duplication is bound to
    the source fingerprint, and the generated notes replace only the freshly
    read copy. The source is never handed to ``replace_midi_clip_notes``.
    """
    _validate_indices(
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
    )
    source_snapshot = client.get_midi_clip(source_track_index, source_scene_index)
    source_fingerprint = _required_fingerprint(source_snapshot)
    source_clip = ableton_snapshot_to_clip(source_snapshot)
    ticks_per_bar = BEATS_PER_BAR * source_clip.ticks_per_beat
    bars, remainder = divmod(source_clip.length_ticks, ticks_per_bar)
    if remainder:
        raise ValueError(
            "Source clip length must be a whole number of 4/4 bars."
        )

    request = MelodyRequest(bpm, root_note, scale, bars, seed)
    plan = build_plan(request, source_clip)
    generated_clip = EditableMidiClip(
        length_ticks=source_clip.length_ticks,
        notes=plan.notes,
        ticks_per_beat=source_clip.ticks_per_beat,
    )
    generated_clip.validate()

    client.duplicate_midi_clip(
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        expected_source_fingerprint=source_fingerprint,
    )
    copy_snapshot = client.get_midi_clip(target_track_index, target_scene_index)
    copy_clip = ableton_snapshot_to_clip(copy_snapshot)
    if copy_clip.length_ticks != generated_clip.length_ticks:
        raise ValueError("Duplicated clip length does not match the source clip.")
    replacement = client.replace_midi_clip_notes(
        target_track_index,
        target_scene_index,
        _required_fingerprint(copy_snapshot),
        clip_notes_to_ableton(generated_clip),
    )
    return _GeneratedCopy(
        source_fingerprint=source_fingerprint,
        bars=bars,
        plan=plan,
        replacement=replacement,
    )


def create_contextual_midi_clip_copy(
    client: AbletonClient,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
) -> ContextualVariationResult:
    """Generate a contextual variation and replace only a protected copy."""
    outcome = _generate_into_protected_copy(
        client,
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        lambda request, source_clip: generate_contextual_plan(request, source_clip),
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        seed=seed,
    )
    return ContextualVariationResult(
        contextualized=True,
        source_track_index=source_track_index,
        source_scene_index=source_scene_index,
        target_track_index=target_track_index,
        target_scene_index=target_scene_index,
        clip_length_beats=outcome.replacement["clip_length_beats"],
        note_count=outcome.replacement["note_count"],
        source_clip_fingerprint=outcome.source_fingerprint,
        target_clip_fingerprint=outcome.replacement["clip_fingerprint"],
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        seed=seed,
    )


def create_bass_line_midi_clip_copy(
    client: AbletonClient,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
    *,
    segment_beats: int = 1,
    velocity: int = DEFAULT_BASS_VELOCITY,
    sustain: bool = False,
    octave: int | None = None,
) -> BassLineClipResult:
    """Generate a diatonic bass line for the source clip into a protected copy.

    The musical work is :func:`generate_bass_line_plan`; this function only
    reads the source, builds the length-matched request, runs the shared
    non-destructive pipeline and echoes the forwarded parameters back. ``root_note``
    and ``scale`` stay an explicit choice of the caller.
    """
    outcome = _generate_into_protected_copy(
        client,
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        lambda request, source_clip: generate_bass_line_plan(
            request,
            source_clip,
            segment_beats=segment_beats,
            velocity=velocity,
            sustain=sustain,
            octave=octave,
        ),
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        seed=seed,
    )
    metadata = outcome.plan.metadata
    return BassLineClipResult(
        generated=True,
        role="bass_line",
        source_track_index=source_track_index,
        source_scene_index=source_scene_index,
        target_track_index=target_track_index,
        target_scene_index=target_scene_index,
        clip_length_beats=outcome.replacement["clip_length_beats"],
        note_count=outcome.replacement["note_count"],
        source_clip_fingerprint=outcome.source_fingerprint,
        target_clip_fingerprint=outcome.replacement["clip_fingerprint"],
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        seed=seed,
        bars=outcome.bars,
        segment_beats=segment_beats,
        velocity=velocity,
        sustain=sustain,
        octave=octave,
        note_grouping=metadata["note_grouping"],
        octave_offset_semitones=metadata["octave_offset_semitones"],
    )


def create_chord_bed_midi_clip_copy(
    client: AbletonClient,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
    *,
    segment_beats: int = 1,
    velocity: int = DEFAULT_CHORD_VELOCITY,
    sustain: bool = False,
    octave: int | None = None,
    chord_size: int = 3,
) -> ChordBedClipResult:
    """Generate a diatonic chord bed for the source clip into a protected copy.

    The musical work is :func:`generate_chord_bed_plan`; this function only
    reads the source, builds the length-matched request, runs the shared
    non-destructive pipeline and echoes the forwarded parameters back. ``root_note``
    and ``scale`` stay an explicit choice of the caller.
    """
    outcome = _generate_into_protected_copy(
        client,
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        lambda request, source_clip: generate_chord_bed_plan(
            request,
            source_clip,
            segment_beats=segment_beats,
            velocity=velocity,
            sustain=sustain,
            octave=octave,
            chord_size=chord_size,
        ),
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        seed=seed,
    )
    metadata = outcome.plan.metadata
    return ChordBedClipResult(
        generated=True,
        role="chord_bed",
        source_track_index=source_track_index,
        source_scene_index=source_scene_index,
        target_track_index=target_track_index,
        target_scene_index=target_scene_index,
        clip_length_beats=outcome.replacement["clip_length_beats"],
        note_count=outcome.replacement["note_count"],
        source_clip_fingerprint=outcome.source_fingerprint,
        target_clip_fingerprint=outcome.replacement["clip_fingerprint"],
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        seed=seed,
        bars=outcome.bars,
        segment_beats=segment_beats,
        velocity=velocity,
        sustain=sustain,
        octave=octave,
        chord_size=chord_size,
        chord_count=metadata["chord_count"],
        voicing=metadata["voicing"],
        note_grouping=metadata["note_grouping"],
        octave_offset_semitones=metadata["octave_offset_semitones"],
    )


def transform_midi_clip_copy(
    client: AbletonClient,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    transform: str,
    semitones: int | None = None,
    grid: str | None = None,
    seed: int | None = None,
    max_timing_shift: float | None = None,
    max_velocity_delta: int | None = None,
    axis_pitch: int | None = None,
    max_duration: float | None = None,
    root_note: str | None = None,
    scale: str | None = None,
    steps: int | None = None,
    start_velocity: int | None = None,
    end_velocity: int | None = None,
) -> TransformedClipResult:
    """Read, preflight, duplicate, transform and replace only the copied clip."""
    _validate_indices(
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
    )
    parameters = _validate_parameters(
        transform,
        semitones,
        grid,
        seed,
        max_timing_shift,
        max_velocity_delta,
        axis_pitch,
        max_duration,
        root_note,
        scale,
        steps,
        start_velocity,
        end_velocity,
    )

    source_snapshot = client.get_midi_clip(source_track_index, source_scene_index)
    source_fingerprint = _required_fingerprint(source_snapshot)
    source_clip = ableton_snapshot_to_clip(source_snapshot)
    _apply_transform(source_clip, transform, parameters)

    client.duplicate_midi_clip(
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        expected_source_fingerprint=source_fingerprint,
    )
    copy_snapshot = client.get_midi_clip(target_track_index, target_scene_index)
    copy_clip = ableton_snapshot_to_clip(copy_snapshot)
    transformed = _apply_transform(copy_clip, transform, parameters)
    replacement = client.replace_midi_clip_notes(
        target_track_index,
        target_scene_index,
        _required_fingerprint(copy_snapshot),
        clip_notes_to_ableton(transformed),
    )
    return TransformedClipResult(
        transformed=True,
        transform=transform,
        source_track_index=source_track_index,
        source_scene_index=source_scene_index,
        target_track_index=target_track_index,
        target_scene_index=target_scene_index,
        clip_length_beats=replacement["clip_length_beats"],
        note_count=replacement["note_count"],
        source_clip_fingerprint=source_fingerprint,
        target_clip_fingerprint=replacement["clip_fingerprint"],
    )


def _apply_transform(clip, transform: str, parameters: dict[str, Any]):
    if transform == "velocity_ramp":
        return velocity_ramp(
            clip, parameters["start_velocity"], parameters["end_velocity"]
        )
    if transform == "harmonize_diatonic":
        return harmonize_diatonic(
            clip, parameters["steps"], parameters["root_note"], parameters["scale"]
        )
    if transform == "transpose_diatonic":
        return transpose_diatonic(
            clip, parameters["steps"], parameters["root_note"], parameters["scale"]
        )
    if transform == "constrain_to_scale":
        return constrain_to_scale(clip, parameters["root_note"], parameters["scale"])
    if transform == "transpose":
        return transpose(clip, parameters["semitones"])
    if transform == "invert":
        return invert(clip, parameters["axis_pitch"])
    if transform == "retrograde":
        return retrograde(clip)
    if transform == "legato":
        return legato(clip)
    if transform == "staccato":
        return staccato(clip, parameters["max_duration_ticks"])
    if transform == "quantize":
        return quantize(clip, parameters["grid"])
    return humanize(
        clip,
        parameters["seed"],
        parameters["max_timing_shift_ticks"],
        parameters["max_velocity_delta"],
    )


def _validate_parameters(
    transform: str,
    semitones: int | None,
    grid: str | None,
    seed: int | None,
    max_timing_shift: float | None,
    max_velocity_delta: int | None,
    axis_pitch: int | None,
    max_duration: float | None,
    root_note: str | None,
    scale: str | None,
    steps: int | None,
    start_velocity: int | None,
    end_velocity: int | None,
) -> dict[str, Any]:
    if transform not in TRANSFORMS:
        raise ValueError(
            "transform must be 'transpose', 'invert', 'retrograde', 'legato', "
            "'staccato', 'constrain_to_scale', 'transpose_diatonic', "
            "'harmonize_diatonic', 'velocity_ramp', 'quantize', or 'humanize'."
        )
    if transform == "transpose":
        if semitones is None:
            raise ValueError("transpose requires semitones.")
        return {"semitones": semitones}
    if transform == "invert":
        if axis_pitch is None:
            raise ValueError("invert requires axis_pitch.")
        return {"axis_pitch": axis_pitch}
    if transform == "retrograde":
        return {}
    if transform == "legato":
        return {}
    if transform == "staccato":
        if max_duration is None:
            raise ValueError("staccato requires max_duration.")
        duration_ticks = beats_to_ticks(max_duration, "max_duration")
        if duration_ticks <= 0:
            raise ValueError("max_duration must convert to at least one tick.")
        return {"max_duration_ticks": duration_ticks}
    if transform == "constrain_to_scale":
        if root_note is None or scale is None:
            raise ValueError("constrain_to_scale requires root_note and scale.")
        return {"root_note": root_note, "scale": scale}
    if transform == "transpose_diatonic":
        if steps is None or root_note is None or scale is None:
            raise ValueError("transpose_diatonic requires steps, root_note and scale.")
        return {"steps": steps, "root_note": root_note, "scale": scale}
    if transform == "harmonize_diatonic":
        if steps is None or root_note is None or scale is None:
            raise ValueError("harmonize_diatonic requires steps, root_note and scale.")
        return {"steps": steps, "root_note": root_note, "scale": scale}
    if transform == "velocity_ramp":
        if start_velocity is None or end_velocity is None:
            raise ValueError(
                "velocity_ramp requires start_velocity and end_velocity."
            )
        for name, value in (
            ("start_velocity", start_velocity),
            ("end_velocity", end_velocity),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 127
            ):
                raise ValueError(f"{name} must be an integer between 1 and 127.")
        return {"start_velocity": start_velocity, "end_velocity": end_velocity}
    if transform == "quantize":
        if grid is None:
            raise ValueError("quantize requires grid.")
        return {"grid": grid}
    if seed is None or max_timing_shift is None or max_velocity_delta is None:
        raise ValueError(
            "humanize requires seed, max_timing_shift, and max_velocity_delta."
        )
    timing_ticks = beats_to_ticks(max_timing_shift, "max_timing_shift")
    return {
        "seed": seed,
        "max_timing_shift_ticks": timing_ticks,
        "max_velocity_delta": max_velocity_delta,
    }


def _validate_indices(*indices: int) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in indices):
        raise ValueError("Track and scene indices must be non-negative integers.")
    if indices[:2] == indices[2:]:
        raise ValueError("Source and target clip slots must be different.")


def _required_fingerprint(snapshot: dict[str, Any]) -> str:
    fingerprint = snapshot.get("clip_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError("Ableton clip snapshot must include a clip_fingerprint.")
    return fingerprint
