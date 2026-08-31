"""Command-line interface for midi-generator."""

from argparse import ArgumentParser
from pathlib import Path

from .domain import TimeSignature
from .domain.music_theory import SCALE_INTERVALS
from .evaluation import evaluate_request
from .exporters import MidiExporter
from .generator import GenerationConfig, generate_midi


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
    parser.add_argument("--output", default="output/melody.mid")
    args = parser.parse_args()
    try:
        time_signature = TimeSignature.parse(args.time_signature)
    except ValueError as error:
        parser.error(str(error))
    if args.candidates is not None and args.candidates < 1:
        parser.error("--candidates must be at least 1.")

    if args.candidates is None:
        path = generate_midi(
            GenerationConfig(
                args.bpm, args.root, args.scale, args.bars, args.seed, time_signature
            ),
            args.output,
        )
        print(f"MIDI created: {Path(path).resolve()}")
        return

    request = GenerationConfig(
        args.bpm, args.root, args.scale, args.bars, args.seed, time_signature
    )
    ranked = evaluate_request(request, args.candidates)
    stem = Path(args.output)
    exporter = MidiExporter()
    for candidate in ranked:
        destination = stem.with_name(
            f"{stem.stem}_rank{candidate.rank:02d}_seed{candidate.seed}{stem.suffix}"
        )
        exporter.export(candidate.plan, destination)
        print(
            f"rank {candidate.rank:>2}  seed {candidate.seed:<12}  "
            f"score {candidate.score.aggregate:.3f}  "
            f"{Path(destination).resolve()}"
        )


if __name__ == "__main__":
    main()
