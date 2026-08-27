"""High-level orchestration for safe Ableton clip transformations."""

from typing import Any, TypedDict

from midi_generator.ableton import AbletonClient
from midi_generator.integration import (
    ableton_snapshot_to_clip,
    beats_to_ticks,
    clip_notes_to_ableton,
)
from midi_generator.transformations import (
    humanize,
    invert,
    legato,
    quantize,
    retrograde,
    staccato,
    transpose,
)

TRANSFORMS = {
    "transpose",
    "invert",
    "retrograde",
    "legato",
    "staccato",
    "quantize",
    "humanize",
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
) -> dict[str, Any]:
    if transform not in TRANSFORMS:
        raise ValueError(
            "transform must be 'transpose', 'invert', 'retrograde', 'legato', "
            "'staccato', 'quantize', or 'humanize'."
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
