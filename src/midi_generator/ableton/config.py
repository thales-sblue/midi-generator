"""Configuration shared by the external Ableton adapter."""

import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 20812
PORT_ENVIRONMENT_VARIABLE = "MIDI_GENERATOR_ABLETON_PORT"


def configured_port() -> int:
    value = os.environ.get(PORT_ENVIRONMENT_VARIABLE)
    if value is None:
        return DEFAULT_PORT
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError(f"{PORT_ENVIRONMENT_VARIABLE} must be an integer.") from error
    validate_port(port)
    return port


def validate_endpoint(host: str, port: int) -> None:
    if host != DEFAULT_HOST:
        raise ValueError("Ableton bridge host must be 127.0.0.1.")
    validate_port(port)


def validate_port(port: int) -> None:
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Ableton bridge port must be between 1 and 65535.")
