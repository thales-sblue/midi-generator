"""Provenance manifest v0 for the heuristic and contextual generators.

This is a versioned record kept *beside* Integration Payload v1, never inside it.
It captures what is needed to reproduce and audit a generation: which backend
and version produced it, the seed, the musical parameters, a hash of the input
context (for contextual generation) and a hash of the produced notes, plus a
caller-supplied timestamp.

The manifest never invents a clock: ``generated_at`` is passed in by the I/O
layer that performs the generation. The deterministic engine stays bit-exact;
only this audit field records wall-clock time.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from midi_generator.domain import CompositionPlan
from midi_generator.transformations import EditableMidiClip

PROVENANCE_SCHEMA_VERSION = 1

HEURISTIC_BACKEND = "heuristic"
CONTEXTUAL_BACKEND = "contextual"

# Bump the matching version whenever a change alters the notes produced for an
# already-supported (seed, parameters) pair. Additive parameters that leave
# existing seeds bit-identical do not require a bump.
BACKEND_VERSIONS = {
    HEURISTIC_BACKEND: "1.0.0",
    CONTEXTUAL_BACKEND: "1.0.0",
}

_REQUIRED_FIELDS = {
    "provenance_schema_version",
    "backend",
    "backend_version",
    "seed",
    "parameters",
    "context_hash",
    "output_hash",
    "generated_at",
}
_REQUIRED_PARAMETER_FIELDS = {
    "bpm",
    "root_note",
    "scale",
    "bars",
    "time_signature",
}


@dataclass(frozen=True)
class ProvenanceManifest:
    """Immutable, JSON-safe provenance record for one generation."""

    provenance_schema_version: int
    backend: str
    backend_version: str
    seed: int
    parameters: dict[str, str | int]
    context_hash: str | None
    output_hash: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provenance_schema_version": self.provenance_schema_version,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "seed": self.seed,
            "parameters": dict(sorted(self.parameters.items())),
            "context_hash": self.context_hash,
            "output_hash": self.output_hash,
            "generated_at": self.generated_at,
        }


def hash_notes(notes: tuple, total_duration_ticks: int) -> str:
    """SHA-256 of the canonical integer-tick representation of a note sequence."""
    canonical = {
        "total_duration_ticks": total_duration_ticks,
        "notes": [
            [
                note.pitch,
                note.start,
                note.duration,
                note.velocity,
                note.channel,
                note.track,
                note.mute,
            ]
            for note in notes
        ],
    }
    return _sha256_json(canonical)


def hash_clip(clip: EditableMidiClip) -> str:
    """SHA-256 of an editable clip: its length plus every note, mute included."""
    clip.validate()
    return hash_notes(clip.notes, clip.length_ticks)


def build_manifest(
    plan: CompositionPlan,
    *,
    generated_at: str,
    reference: EditableMidiClip | None = None,
) -> ProvenanceManifest:
    """Derive a provenance manifest from a finished plan.

    The backend is read from ``plan.metadata['generation_mode']`` ("contextual"
    when contextual generation set it, "heuristic" otherwise). Pass ``reference``
    for contextual generation so the input context is hashed.
    """
    backend = (
        CONTEXTUAL_BACKEND
        if plan.metadata.get("generation_mode") == "contextual"
        else HEURISTIC_BACKEND
    )
    request = plan.request
    manifest = ProvenanceManifest(
        provenance_schema_version=PROVENANCE_SCHEMA_VERSION,
        backend=backend,
        backend_version=BACKEND_VERSIONS[backend],
        seed=plan.seed,
        parameters={
            "bpm": request.bpm,
            "root_note": request.root_note,
            "scale": request.scale,
            "bars": request.bars,
            "time_signature": str(request.time_signature),
        },
        context_hash=hash_clip(reference) if reference is not None else None,
        output_hash=hash_notes(plan.notes, plan.total_duration_ticks),
        generated_at=_validated_timestamp(generated_at),
    )
    validate_manifest(manifest.to_dict())
    return manifest


def validate_manifest(manifest: dict[str, object]) -> None:
    """Validate the structural guarantees of a provenance manifest v0 dict."""
    missing = _REQUIRED_FIELDS.difference(manifest)
    if missing:
        raise ValueError(
            f"Provenance manifest is missing fields: {', '.join(sorted(missing))}."
        )
    if manifest["provenance_schema_version"] != PROVENANCE_SCHEMA_VERSION:
        raise ValueError(
            f"provenance_schema_version must be {PROVENANCE_SCHEMA_VERSION}."
        )
    if manifest["backend"] not in BACKEND_VERSIONS:
        raise ValueError(
            f"backend must be one of: {', '.join(sorted(BACKEND_VERSIONS))}."
        )
    if not _is_nonempty_str(manifest["backend_version"]):
        raise ValueError("backend_version must be a non-empty string.")
    if not _is_int(manifest["seed"]):
        raise ValueError("seed must be an integer.")
    if not _is_nonempty_str(manifest["output_hash"]):
        raise ValueError("output_hash must be a non-empty string.")
    if manifest["context_hash"] is not None and not _is_nonempty_str(
        manifest["context_hash"]
    ):
        raise ValueError("context_hash must be null or a non-empty string.")
    if not _is_nonempty_str(manifest["generated_at"]):
        raise ValueError("generated_at must be a non-empty ISO 8601 string.")

    parameters = manifest["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object.")
    missing_parameters = _REQUIRED_PARAMETER_FIELDS.difference(parameters)
    if missing_parameters:
        raise ValueError(
            "parameters is missing fields: "
            f"{', '.join(sorted(missing_parameters))}."
        )


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_timestamp(value: str) -> str:
    if not _is_nonempty_str(value):
        raise ValueError("generated_at must be a non-empty ISO 8601 string.")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            "generated_at must be an ISO 8601 timestamp."
        ) from error
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
