"""Musical composition algorithms."""

from .contextual import generate_contextual_plan
from .melody import generate_plan

__all__ = ["generate_contextual_plan", "generate_plan"]
