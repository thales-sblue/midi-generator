"""Read-back verification harness for the Ableton MIDI-clip operation gate.

This is the instrument for the manual Live gate. For one bridge operation it
runs the real orchestration, reads the source and target clips back, and
checks structurally that the target holds exactly what the deterministic
engine intended while the source stays untouched. It adds no musical
algorithm: it reuses the orchestration in :mod:`ableton_transform` and the
same domain functions that orchestration uses, so ``expected`` means "what
the pipeline meant to write" and the novel assertion is that the Live
round-trip preserved it.

Run against a live set with the bridge active::

    $env:PYTHONPATH = "src"
    python -m midi_generator.mcp.verification --source 0 0 --target 0 1
"""

from __future__ import annotations

import json
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import Any, Callable

from midi_generator.ableton import AbletonClient, AbletonError
from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_contextual_plan
from midi_generator.generation.melody import BEATS_PER_BAR
from midi_generator.integration import ableton_snapshot_to_clip, clip_notes_to_ableton
from midi_generator.transformations import EditableMidiClip

# `_apply_transform` / `_validate_parameters` are private, but the reuse is
# deliberate: they are exactly the steps the orchestration runs, so "expected"
# stays "what the pipeline meant to write" instead of a parallel re-derivation.
from midi_generator.mcp.ableton_transform import (
    _apply_transform,
    _validate_parameters,
    create_contextual_midi_clip_copy,
    transform_midi_clip_copy,
)

_TRANSFORM_OPS = (
    "constrain_to_scale",
    "transpose_diatonic",
    "harmonize_diatonic",
    "velocity_ramp",
)
_CONTEXTUAL_OP = "create_contextual_variation_from_ableton_clip"
_ALL_OPS = _TRANSFORM_OPS + (_CONTEXTUAL_OP,)


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class VerificationReport:
    operation: str
    checks: tuple[VerificationCheck, ...]
    evidence: dict[str, Any]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def checks_by_name(self) -> dict[str, VerificationCheck]:
        return {check.name: check for check in self.checks}

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "passed": self.passed,
            "checks": [check.as_dict() for check in self.checks],
            "evidence": self.evidence,
        }


def _sorted_notes(clip: EditableMidiClip) -> list[dict[str, Any]]:
    return sorted(
        clip_notes_to_ableton(clip),
        key=lambda note: (
            note["start_time"],
            note["pitch"],
            note["duration"],
            note["velocity"],
            note["mute"],
        ),
    )


def _first_diff(
    expected: list[dict[str, Any]], actual: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for index in range(max(len(expected), len(actual))):
        want = expected[index] if index < len(expected) else None
        got = actual[index] if index < len(actual) else None
        if want != got:
            return {"index": index, "expected": want, "actual": got}
    return None


def _roundtrip_checks(
    operation: str,
    client: Any,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    run_orchestration: Callable[[], dict[str, Any]],
    expected_from_source: Callable[[EditableMidiClip], EditableMidiClip],
) -> VerificationReport:
    checks: list[VerificationCheck] = []
    evidence: dict[str, Any] = {"first_note_diff": None}

    source_before = client.get_midi_clip(source_track_index, source_scene_index)
    evidence["source_fingerprint_before"] = source_before.get("clip_fingerprint")
    source_clip = ableton_snapshot_to_clip(source_before)

    result: dict[str, Any] | None
    try:
        result = run_orchestration()
        succeeded = bool(result.get("transformed") or result.get("contextualized"))
        checks.append(
            VerificationCheck(
                "orchestration_succeeded",
                succeeded,
                "" if succeeded else f"orchestration returned {result!r}",
            )
        )
    except (ValueError, AbletonError) as error:
        result = None
        checks.append(VerificationCheck("orchestration_succeeded", False, str(error)))

    source_after = client.get_midi_clip(source_track_index, source_scene_index)
    evidence["source_fingerprint_after"] = source_after.get("clip_fingerprint")
    preserved = source_before.get("clip_fingerprint") == source_after.get(
        "clip_fingerprint"
    ) and source_before.get("notes") == source_after.get("notes")
    checks.append(
        VerificationCheck(
            "source_preserved",
            preserved,
            "" if preserved else "source clip changed during the operation",
        )
    )

    try:
        expected_clip = expected_from_source(source_clip)
        expected_notes = _sorted_notes(expected_clip)
        evidence["expected_note_count"] = len(expected_notes)
    except (ValueError, AbletonError) as error:
        checks.append(
            VerificationCheck(
                "target_matches_expected",
                False,
                f"could not compute the expected clip: {error}",
            )
        )
        checks.append(
            VerificationCheck(
                "reported_fingerprint_matches_readback", False, "not evaluated"
            )
        )
        return VerificationReport(operation, tuple(checks), evidence)

    if result is None:
        checks.append(
            VerificationCheck(
                "target_matches_expected", False, "orchestration did not run"
            )
        )
        checks.append(
            VerificationCheck(
                "reported_fingerprint_matches_readback", False, "not evaluated"
            )
        )
        return VerificationReport(operation, tuple(checks), evidence)

    target_after = client.get_midi_clip(target_track_index, target_scene_index)
    evidence["target_fingerprint"] = target_after.get("clip_fingerprint")
    target_clip = ableton_snapshot_to_clip(target_after)
    target_notes = _sorted_notes(target_clip)
    evidence["target_note_count"] = len(target_notes)

    length_match = target_clip.length_ticks == expected_clip.length_ticks
    diff = _first_diff(expected_notes, target_notes)
    evidence["first_note_diff"] = diff
    matches = length_match and diff is None
    detail_parts = []
    if not length_match:
        detail_parts.append(
            f"length expected {expected_clip.length_ticks} "
            f"got {target_clip.length_ticks}"
        )
    if diff is not None:
        detail_parts.append(f"first diff at index {diff['index']}")
    checks.append(
        VerificationCheck(
            "target_matches_expected", matches, "; ".join(detail_parts)
        )
    )

    reported = result.get("target_clip_fingerprint")
    readback = target_after.get("clip_fingerprint")
    fingerprint_match = reported == readback
    checks.append(
        VerificationCheck(
            "reported_fingerprint_matches_readback",
            fingerprint_match,
            ""
            if fingerprint_match
            else f"reported {reported!r} but read back {readback!r}",
        )
    )

    return VerificationReport(operation, tuple(checks), evidence)


def verify_transform_roundtrip(
    client: Any,
    *,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    transform: str,
    semitones: int | None = None,
    grid: str | None = None,
    seed: int | None = None,
    max_timing_shift: float | None = None,
    max_velocity_delta: int | None = None,
    axis_pitch: int | None = None,
    max_duration: float | None = None,
    root_note: str | None = None,
    scale: str | None = None,
    steps: int | None = None,
    start_velocity: int | None = None,
    end_velocity: int | None = None,
) -> VerificationReport:
    """Run one transform through the bridge and verify the written copy."""
    passthrough = dict(
        semitones=semitones,
        grid=grid,
        seed=seed,
        max_timing_shift=max_timing_shift,
        max_velocity_delta=max_velocity_delta,
        axis_pitch=axis_pitch,
        max_duration=max_duration,
        root_note=root_note,
        scale=scale,
        steps=steps,
        start_velocity=start_velocity,
        end_velocity=end_velocity,
    )

    def run_orchestration() -> dict[str, Any]:
        return transform_midi_clip_copy(
            client,
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            transform,
            **passthrough,
        )

    def expected_from_source(source_clip: EditableMidiClip) -> EditableMidiClip:
        parameters = _validate_parameters(
            transform,
            semitones,
            grid,
            seed,
            max_timing_shift,
            max_velocity_delta,
            axis_pitch,
            max_duration,
            root_note,
            scale,
            steps,
            start_velocity,
            end_velocity,
        )
        return _apply_transform(source_clip, transform, parameters)

    return _roundtrip_checks(
        transform,
        client,
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        run_orchestration,
        expected_from_source,
    )


def verify_contextual_roundtrip(
    client: Any,
    *,
    source_track_index: int,
    source_scene_index: int,
    target_track_index: int,
    target_scene_index: int,
    bpm: int,
    root_note: str,
    scale: str,
    seed: int,
) -> VerificationReport:
    """Run the contextual variation through the bridge and verify the copy."""

    def run_orchestration() -> dict[str, Any]:
        return create_contextual_midi_clip_copy(
            client,
            source_track_index,
            source_scene_index,
            target_track_index,
            target_scene_index,
            bpm,
            root_note,
            scale,
            seed,
        )

    def expected_from_source(source_clip: EditableMidiClip) -> EditableMidiClip:
        ticks_per_bar = BEATS_PER_BAR * source_clip.ticks_per_beat
        bars, remainder = divmod(source_clip.length_ticks, ticks_per_bar)
        if remainder:
            raise ValueError(
                "Source clip length must be a whole number of 4/4 bars."
            )
        plan = generate_contextual_plan(
            MelodyRequest(bpm, root_note, scale, bars, seed), source_clip
        )
        expected = EditableMidiClip(
            length_ticks=source_clip.length_ticks,
            notes=plan.notes,
            ticks_per_beat=source_clip.ticks_per_beat,
        )
        expected.validate()
        return expected

    return _roundtrip_checks(
        _CONTEXTUAL_OP,
        client,
        source_track_index,
        source_scene_index,
        target_track_index,
        target_scene_index,
        run_orchestration,
        expected_from_source,
    )


def _run_operation(
    client: Any,
    operation: str,
    source: tuple[int, int],
    target: tuple[int, int],
    params: dict[str, Any],
) -> VerificationReport:
    source_track, source_scene = source
    target_track, target_scene = target
    try:
        if operation == _CONTEXTUAL_OP:
            return verify_contextual_roundtrip(
                client,
                source_track_index=source_track,
                source_scene_index=source_scene,
                target_track_index=target_track,
                target_scene_index=target_scene,
                bpm=params["bpm"],
                root_note=params["root_note"],
                scale=params["scale"],
                seed=params["seed"],
            )
        return verify_transform_roundtrip(
            client,
            source_track_index=source_track,
            source_scene_index=source_scene,
            target_track_index=target_track,
            target_scene_index=target_scene,
            transform=operation,
            root_note=params["root_note"],
            scale=params["scale"],
            steps=params["steps"],
            start_velocity=params["start_velocity"],
            end_velocity=params["end_velocity"],
        )
    except (ValueError, AbletonError) as error:
        return VerificationReport(
            operation,
            (VerificationCheck("operation_completed", False, str(error)),),
            {"first_note_diff": None},
        )


def _print_report(report: VerificationReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    print(f"[{status}] {report.operation}")
    for check in report.checks:
        mark = "ok  " if check.passed else "FAIL"
        suffix = f" - {check.detail}" if check.detail else ""
        print(f"    {mark} {check.name}{suffix}")
    evidence = report.evidence
    print(
        "    evidence: "
        f"source_fp {evidence.get('source_fingerprint_before')} -> "
        f"{evidence.get('source_fingerprint_after')}; "
        f"target_fp {evidence.get('target_fingerprint')}; "
        f"notes expected {evidence.get('expected_note_count')} "
        f"got {evidence.get('target_note_count')}"
    )
    if evidence.get("first_note_diff") is not None:
        print(f"    first_note_diff: {evidence['first_note_diff']}")


def _parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m midi_generator.mcp.verification",
        description="Read-back verification for the Ableton clip-operation gate.",
    )
    parser.add_argument(
        "--source",
        nargs=2,
        type=int,
        required=True,
        metavar=("TRACK", "SCENE"),
        help="Source MIDI clip slot (Session View).",
    )
    parser.add_argument(
        "--target",
        nargs=2,
        type=int,
        required=True,
        metavar=("TRACK", "SCENE"),
        help=(
            "Target clip slot. With --op it is used as-is; without --op the "
            "five operations write to SCENE, SCENE+1, ... (five empty slots)."
        ),
    )
    parser.add_argument("--op", choices=_ALL_OPS, help="Verify only this operation.")
    parser.add_argument("--root-note", default="C")
    parser.add_argument("--scale", default="major")
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--start-velocity", type=int, default=40)
    parser.add_argument("--end-velocity", type=int, default=120)
    parser.add_argument("--bpm", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        client = AbletonClient()
        client.ping()
    except (AbletonError, ValueError) as error:
        print(f"Ableton bridge unavailable: {error}")
        raise SystemExit(1)

    operations = [args.op] if args.op else list(_ALL_OPS)
    params = {
        "root_note": args.root_note,
        "scale": args.scale,
        "steps": args.steps,
        "start_velocity": args.start_velocity,
        "end_velocity": args.end_velocity,
        "bpm": args.bpm,
        "seed": args.seed,
    }
    source = (args.source[0], args.source[1])
    reports = []
    for index, operation in enumerate(operations):
        target_scene = args.target[1] if args.op else args.target[1] + index
        reports.append(
            _run_operation(
                client, operation, source, (args.target[0], target_scene), params
            )
        )

    if args.json:
        print(json.dumps([report.as_dict() for report in reports], indent=2))
    else:
        for report in reports:
            _print_report(report)

    raise SystemExit(0 if all(report.passed for report in reports) else 1)


if __name__ == "__main__":
    main()
