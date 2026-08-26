"""The complete musical result before it is exported anywhere."""

from dataclasses import dataclass, field

from .generation_report import GenerationReport
from .note_event import NoteEvent
from .requests import MelodyRequest


@dataclass(frozen=True)
class CompositionPlan:
    request: MelodyRequest
    seed: int
    notes: tuple[NoteEvent, ...]
    total_duration_ticks: int
    report: GenerationReport
    metadata: dict[str, str | int] = field(default_factory=dict)
