"""Input requested from the melody-generation engine."""

from dataclasses import dataclass, field

from .time_signature import TimeSignature


@dataclass(frozen=True)
class MelodyRequest:
    bpm: int
    root_note: str
    scale: str
    bars: int
    seed: int
    time_signature: TimeSignature = field(default_factory=lambda: TimeSignature(4, 4))

    def validate(self) -> None:
        if not 20 <= self.bpm <= 400:
            raise ValueError("BPM must be between 20 and 400.")
        if self.bars < 1:
            raise ValueError("Bars must be at least 1.")
        if not isinstance(self.time_signature, TimeSignature):
            raise ValueError("time_signature must be a TimeSignature instance.")
