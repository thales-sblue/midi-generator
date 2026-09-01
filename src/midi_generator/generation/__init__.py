"""Musical composition algorithms."""

from .bass_line import generate_bass_line_plan
from .contextual import generate_contextual_plan
from .melody import generate_plan

__all__ = [
    "generate_bass_line_plan",
    "generate_contextual_plan",
    "generate_plan",
]
