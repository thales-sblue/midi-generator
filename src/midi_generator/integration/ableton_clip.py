"""Conversions between Ableton clip snapshots and the transformation domain."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from midi_generator.domain import NoteEvent
from midi_generator.transformations.clip import EditableMidiClip, TICKS_PER_BEAT


def ableton_snapshot_to_clip(snapshot: dict[str, Any]) -> EditableMidiClip:
    """Validate a bridge snapshot and convert beat times to integer ticks."""
    if not isinstance(snapshot, dict):
        raise ValueError("Ableton clip snapshot must be an object.")
    length_ticks = beats_to_ticks(snapshot.get("clip_length_beats"), "clip_length_beats")
    if length_ticks <= 0:
        raise ValueError("clip_length_beats must be positive.")
    raw_notes = snapshot.get("notes")
    if not isinstance(raw_notes, list):
        raise ValueError("Ableton clip notes must be a list.")

    notes = []
    for index, raw_note in enumerate(raw_notes):
        if not isinstance(raw_note, dict):
            raise ValueError(f"Note {index} must be an object.")
        missing = {
            "pitch", "start_time", "duration", "velocity", "mute"
        }.difference(raw_note)
        if missing:
            raise ValueError(f"Note {index} is missing {sorted(missing)[0]}.")
        notes.append(
            NoteEvent(
                pitch=raw_note["pitch"],
                start=beats_to_ticks(raw_note["start_time"], f"Note {index} start_time"),
                duration=beats_to_ticks(raw_note["duration"], f"Note {index} duration"),
                velocity=raw_note["velocity"],
                mute=raw_note["mute"],
            )
        )
    clip = EditableMidiClip(length_ticks=length_ticks, notes=tuple(notes))
    clip.validate()
    return clip


def clip_notes_to_ableton(clip: EditableMidiClip) -> list[dict[str, Any]]:
    """Serialize domain notes into the bridge's beat-based note contract."""
    clip.validate()
    return [
        {
            "pitch": note.pitch,
            "start_time": ticks_to_beats(note.start),
            "duration": ticks_to_beats(note.duration),
            "velocity": note.velocity,
            "mute": note.mute,
        }
        for note in clip.notes
    ]


def beats_to_ticks(value: object, field: str = "beats") -> int:
    """Convert decimal beats deterministically using half-up tick rounding."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"{field} must be a finite number.")
    try:
        beats = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{field} must be a finite number.") from error
    if not beats.is_finite() or beats < 0:
        raise ValueError(f"{field} must be a non-negative finite number.")
    return int((beats * TICKS_PER_BEAT).to_integral_value(rounding=ROUND_HALF_UP))


def ticks_to_beats(ticks: int) -> float:
    return float(Decimal(ticks) / Decimal(TICKS_PER_BEAT))
