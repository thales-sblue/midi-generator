"""Serialization of composition plans to Integration Payload v1."""

from typing import TypedDict

from midi_generator.domain import CompositionPlan

SCHEMA_VERSION = 1
REQUIRED_PAYLOAD_FIELDS = {
    "schema_version",
    "bpm",
    "root_note",
    "scale",
    "bars",
    "seed",
    "time_signature",
    "ticks_per_beat",
    "total_duration_ticks",
    "notes",
    "report",
    "metadata",
}
REQUIRED_NOTE_FIELDS = {
    "pitch",
    "start",
    "duration",
    "velocity",
    "channel",
    "track",
}


class NotePayload(TypedDict):
    pitch: int
    start: int
    duration: int
    velocity: int
    channel: int
    track: int


class ReportPayload(TypedDict):
    note_count: int
    pause_count: int
    duration_ticks: int
    scale: str
    seed: int
    warnings: list[str]


class IntegrationPayload(TypedDict):
    schema_version: int
    bpm: int
    root_note: str
    scale: str
    bars: int
    seed: int
    time_signature: str
    ticks_per_beat: int
    total_duration_ticks: int
    notes: list[NotePayload]
    report: ReportPayload
    metadata: dict[str, str | int]


def composition_to_payload(plan: CompositionPlan) -> IntegrationPayload:
    """Convert a composition plan into the stable JSON-safe v1 contract."""
    request = plan.request
    report = plan.report
    time_signature = plan.metadata.get("time_signature")
    ticks_per_beat = plan.metadata.get("ticks_per_beat")
    if not isinstance(time_signature, str) or not time_signature.strip():
        raise ValueError("Composition plan must define a non-empty time_signature.")
    if (
        not isinstance(ticks_per_beat, int)
        or isinstance(ticks_per_beat, bool)
        or ticks_per_beat <= 0
    ):
        raise ValueError("Composition plan must define a positive ticks_per_beat.")

    payload = IntegrationPayload(
        schema_version=SCHEMA_VERSION,
        bpm=request.bpm,
        root_note=request.root_note,
        scale=request.scale,
        bars=request.bars,
        seed=plan.seed,
        time_signature=time_signature,
        ticks_per_beat=ticks_per_beat,
        total_duration_ticks=plan.total_duration_ticks,
        notes=[
            NotePayload(
                pitch=note.pitch,
                start=note.start,
                duration=note.duration,
                velocity=note.velocity,
                channel=note.channel,
                track=note.track,
            )
            for note in plan.notes
        ],
        report=ReportPayload(
            note_count=report.note_count,
            pause_count=report.pause_count,
            duration_ticks=report.duration_ticks,
            scale=report.scale,
            seed=report.seed,
            warnings=list(report.warnings),
        ),
        metadata=dict(sorted(plan.metadata.items())),
    )
    validate_payload_v1(payload)
    return payload


def validate_payload_v1(payload: IntegrationPayload) -> None:
    """Validate the structural guarantees made by Integration Payload v1."""
    missing_payload_fields = REQUIRED_PAYLOAD_FIELDS.difference(payload)
    if missing_payload_fields:
        fields = ", ".join(sorted(missing_payload_fields))
        raise ValueError(f"Payload v1 is missing required fields: {fields}.")

    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}.")
    if not _is_int(payload["bpm"]) or not 20 <= payload["bpm"] <= 400:
        raise ValueError("BPM must be between 20 and 400.")
    if not _is_int(payload["bars"]) or payload["bars"] < 1:
        raise ValueError("Bars must be at least 1.")
    if not isinstance(payload["time_signature"], str) or not payload[
        "time_signature"
    ].strip():
        raise ValueError("time_signature must be present.")
    if not _is_int(payload["ticks_per_beat"]) or payload["ticks_per_beat"] <= 0:
        raise ValueError("ticks_per_beat must be positive.")
    if (
        not _is_int(payload["total_duration_ticks"])
        or payload["total_duration_ticks"] <= 0
    ):
        raise ValueError("total_duration_ticks must be positive.")
    if not isinstance(payload["notes"], list):
        raise ValueError("notes must be a list.")

    for index, note in enumerate(payload["notes"]):
        if not isinstance(note, dict):
            raise ValueError(f"Note {index} must be an object.")
        missing = REQUIRED_NOTE_FIELDS.difference(note)
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"Note {index} is missing required fields: {fields}.")
        if not _is_int(note["pitch"]) or not 0 <= note["pitch"] <= 127:
            raise ValueError(f"Note {index} pitch must be between 0 and 127.")
        if not _is_int(note["velocity"]) or not 1 <= note["velocity"] <= 127:
            raise ValueError(f"Note {index} velocity must be between 1 and 127.")
        if not _is_int(note["duration"]) or note["duration"] <= 0:
            raise ValueError(f"Note {index} duration must be positive.")
        if not _is_int(note["start"]) or note["start"] < 0:
            raise ValueError(f"Note {index} start must not be negative.")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
