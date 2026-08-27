"""External adapter for the local Ableton Live bridge."""

from .client import AbletonClient
from .config import DEFAULT_HOST, DEFAULT_PORT
from .errors import (
    AbletonCommandError,
    AbletonError,
    AbletonProtocolError,
    AbletonTimeoutError,
    AbletonUnavailableError,
)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "AbletonClient",
    "AbletonCommandError",
    "AbletonError",
    "AbletonProtocolError",
    "AbletonTimeoutError",
    "AbletonUnavailableError",
]
