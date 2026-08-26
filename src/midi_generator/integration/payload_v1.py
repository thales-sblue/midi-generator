"""Serialization of composition plans to Integration Payload v1."""

from typing import TypedDict

from midi_generator.domain import CompositionPlan

SCHEMA_VERSION = 1


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
    total_duration_ticks: int
    notes: list[NotePayload]
    report: ReportPayload
    metadata: dict[str, str | int]


def composition_to_payload(plan: CompositionPlan) -> IntegrationPayload:
    """Convert a composition plan into the stable JSON-safe v1 contract."""
    request = plan.request
    report = plan.report
    return IntegrationPayload(
        schema_version=SCHEMA_VERSION,
        bpm=request.bpm,
        root_note=request.root_note,
        scale=request.scale,
        bars=request.bars,
        seed=plan.seed,
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
