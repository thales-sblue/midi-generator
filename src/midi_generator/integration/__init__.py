"""Stable, JSON-safe contracts for external integrations."""

from .payload_v1 import (
    SCHEMA_VERSION,
    IntegrationPayload,
    NotePayload,
    ReportPayload,
    composition_to_payload,
    validate_payload_v1,
)

__all__ = [
    "SCHEMA_VERSION",
    "IntegrationPayload",
    "NotePayload",
    "ReportPayload",
    "composition_to_payload",
    "validate_payload_v1",
]
