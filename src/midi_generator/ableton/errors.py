"""Explicit failures raised by the external Ableton adapter."""


class AbletonError(Exception):
    """Base class for expected Ableton integration failures."""


class AbletonUnavailableError(AbletonError):
    """The local Ableton bridge cannot be reached."""


class AbletonTimeoutError(AbletonUnavailableError):
    """The bridge did not answer before the configured timeout."""


class AbletonProtocolError(AbletonError):
    """The bridge returned malformed or mismatched protocol data."""


class AbletonCommandError(AbletonError):
    """The bridge rejected a well-formed command."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
