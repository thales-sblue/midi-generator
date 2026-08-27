"""MCP communication layer for the melody engine."""

from .server import (
    generate_and_insert_melody,
    generate_melody,
    get_ableton_session,
    mcp,
)

__all__ = [
    "generate_and_insert_melody",
    "generate_melody",
    "get_ableton_session",
    "mcp",
]
