"""Library-independent model for MIDI clip transformations."""

from dataclasses import dataclass

from midi_generator.domain import NoteEvent

TICKS_PER_BEAT = 480


@dataclass(frozen=True)
class EditableMidiClip:
    """An immutable 4/4 MIDI clip whose note times are integer ticks."""

    length_ticks: int
    notes: tuple[NoteEvent, ...]
    ticks_per_beat: int = TICKS_PER_BEAT

    def validate(self) -> None:
        if not _is_int(self.length_ticks) or self.length_ticks <= 0:
            raise ValueError("Clip length must be a positive integer number of ticks.")
        if self.ticks_per_beat != TICKS_PER_BEAT:
            raise ValueError(f"ticks_per_beat must be {TICKS_PER_BEAT}.")
        if not isinstance(self.notes, tuple):
            raise ValueError("Clip notes must be a tuple.")
        for index, note in enumerate(self.notes):
            if not isinstance(note, NoteEvent):
                raise ValueError(f"Note {index} must be a NoteEvent.")
            if not _is_int(note.pitch) or not 0 <= note.pitch <= 127:
                raise ValueError(f"Note {index} pitch must be between 0 and 127.")
            if not _is_int(note.start) or note.start < 0:
                raise ValueError(f"Note {index} start must not be negative.")
            if not _is_int(note.duration) or note.duration <= 0:
                raise ValueError(f"Note {index} duration must be positive.")
            if note.start + note.duration > self.length_ticks:
                raise ValueError(f"Note {index} extends beyond the clip length.")
            if not _is_int(note.velocity) or not 1 <= note.velocity <= 127:
                raise ValueError(f"Note {index} velocity must be between 1 and 127.")
            if not isinstance(note.mute, bool):
                raise ValueError(f"Note {index} mute must be boolean.")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
