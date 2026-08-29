"""Stable, JSON-safe contracts for external integrations."""

from .ableton_clip import (
    ableton_snapshot_to_clip,
    beats_to_ticks,
    clip_notes_to_ableton,
    ticks_to_beats,
)
from .clip_profile import ClipProfilePayload, clip_profile_to_payload
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
    "ableton_snapshot_to_clip",
    "beats_to_ticks",
    "clip_notes_to_ableton",
    "ticks_to_beats",
    "ClipProfilePayload",
    "clip_profile_to_payload",
]
