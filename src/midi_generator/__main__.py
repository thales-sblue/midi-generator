"""Command-line interface for midi-generator."""

import json
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path

from .domain import TimeSignature
from .domain.music_theory import SCALE_INTERVALS
from .evaluation import evaluate_request
from .exporters import MidiExporter
from .generation import generate_plan
from .generator import GenerationConfig
from .provenance import build_manifest


def main() -> None:
    parser = ArgumentParser(description="Generate a deterministic MIDI melody.")
    parser.add_argument("--bpm", type=int, required=True)
    parser.add_argument("--root", required=True, help="Example: C, F#, Bb")
    parser.add_argument("--scale", choices=tuple(SCALE_INTERVALS), required=True)
    parser.add_argument("--bars", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--time-signature",
        default="4/4",
        help="Meter such as 4/4, 3/4 or 6/8 (default: 4/4).",
    )
    parser.add_argument(
        "--candidates",
        type=int,
        default=None,
        help=(
            "Generate N candidates from seeds derived from --seed, score them "
            "and write one ranked MIDI file per candidate."
        ),
    )
    parser.add_argument(
        "--provenance",
        action="store_true",
        help=(
            "Write a provenance manifest (<output>.provenance.json) beside each "
            "MIDI file."
        ),
    )
    parser.add_argument("--output", default="output/melody.mid")
    args = parser.parse_args()
    try:
        time_signature = TimeSignature.parse(args.time_signature)
    except ValueError as error:
        parser.error(str(error))
    if args.candidates is not None and args.candidates < 1:
        parser.error("--candidates must be at least 1.")

    request = GenerationConfig(
        args.bpm, args.root, args.scale, args.bars, args.seed, time_signature
    )
    exporter = MidiExporter()
    generated_at = datetime.now(timezone.utc).isoformat()

    if args.candidates is None:
        plan = generate_plan(request)
        destination = Path(args.output)
        exporter.export(plan, destination)
        print(f"MIDI created: {destination.resolve()}")
        if args.provenance:
            manifest_path = _write_manifest(plan, destination, generated_at)
            print(f"Provenance written: {manifest_path.resolve()}")
        return

    ranked = evaluate_request(request, args.candidates)
    stem = Path(args.output)
    for candidate in ranked:
        destination = stem.with_name(
            f"{stem.stem}_rank{candidate.rank:02d}_seed{candidate.seed}{stem.suffix}"
        )
        exporter.export(candidate.plan, destination)
        line = (
            f"rank {candidate.rank:>2}  seed {candidate.seed:<12}  "
            f"score {candidate.score.aggregate:.3f}  {destination.resolve()}"
        )
        if args.provenance:
            _write_manifest(candidate.plan, destination, generated_at)
        print(line)


def _write_manifest(plan, midi_path: Path, generated_at: str) -> Path:
    manifest = build_manifest(plan, generated_at=generated_at)
    manifest_path = midi_path.with_suffix(midi_path.suffix + ".provenance.json")
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


if __name__ == "__main__":
    main()
