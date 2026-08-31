"""Time signature value object, independent of MIDI file libraries."""

from dataclasses import dataclass

_QUARTER_NOTE_DENOMINATOR = 4
_SUPPORTED_DENOMINATORS = (1, 2, 4, 8, 16)


@dataclass(frozen=True)
class TimeSignature:
    """An immutable ``numerator/denominator`` meter such as ``3/4`` or ``6/8``."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if not isinstance(self.numerator, int) or not isinstance(self.denominator, int):
            raise ValueError("Time signature numerator and denominator must be integers.")
        if self.numerator < 1:
            raise ValueError("Time signature numerator must be at least 1.")
        if self.denominator not in _SUPPORTED_DENOMINATORS:
            raise ValueError(
                "Time signature denominator must be one of "
                f"{', '.join(str(value) for value in _SUPPORTED_DENOMINATORS)}."
            )

    @classmethod
    def parse(cls, text: str) -> "TimeSignature":
        """Build a time signature from text like ``"3/4"``."""
        parts = text.strip().split("/")
        if len(parts) != 2 or not all(part.strip().lstrip("+").isdigit() for part in parts):
            raise ValueError(f"Time signature must look like '3/4', got {text!r}.")
        return cls(int(parts[0]), int(parts[1]))

    def bar_ticks(self, ticks_per_beat: int) -> int:
        """Ticks in one bar, where ``ticks_per_beat`` counts a quarter note."""
        numerator_ticks = self.numerator * ticks_per_beat * _QUARTER_NOTE_DENOMINATOR
        bar, remainder = divmod(numerator_ticks, self.denominator)
        if remainder:
            raise ValueError(
                f"{self} does not divide into whole ticks at "
                f"{ticks_per_beat} ticks per beat."
            )
        return bar

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"
