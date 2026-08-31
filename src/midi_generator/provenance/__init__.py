"""Provenance manifest v0 — a versioned audit record beside Integration Payload v1.

It is never merged into the payload: it lives in its own schema so backend,
version, seed, parameters, context hash, output hash and timestamp can evolve
independently of the integration contract.
"""

from .manifest import (
    BACKEND_VERSIONS,
    CONTEXTUAL_BACKEND,
    HEURISTIC_BACKEND,
    PROVENANCE_SCHEMA_VERSION,
    ProvenanceManifest,
    build_manifest,
    hash_clip,
    hash_notes,
    validate_manifest,
)

__all__ = [
    "BACKEND_VERSIONS",
    "CONTEXTUAL_BACKEND",
    "HEURISTIC_BACKEND",
    "PROVENANCE_SCHEMA_VERSION",
    "ProvenanceManifest",
    "build_manifest",
    "hash_clip",
    "hash_notes",
    "validate_manifest",
]
