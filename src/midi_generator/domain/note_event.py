"""Library-independent representation of a MIDI note."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    pitch: int
    start: int
    duration: int
    velocity: int
    channel: int = 0
    track: int = 0
    mute: bool = False
