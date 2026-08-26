"""Small summary of a completed generation run."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GenerationReport:
    note_count: int
    pause_count: int
    duration_ticks: int
    scale: str
    seed: int
    warnings: tuple[str, ...] = field(default_factory=tuple)
