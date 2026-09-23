"""Command line for audio analysis and accompaniment.

    python -m midi_generator.audio analyze guitar.wav [--json]
    python -m midi_generator.audio accompany guitar.wav [--output-dir output]
"""

import json
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from midi_generator.domain import MusicAnalysis
from midi_generator.exporters import export_accompaniment
from midi_generator.generation import DRUM_STYLES, generate_accompaniment

from .analyzer import analyze_audio


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(
        prog="python -m midi_generator.audio",
        description="Analyse a recording and generate MIDI that accompanies it.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    analyze = commands.add_parser("analyze", help="Print tempo, metre, key and chords.")
    _add_analysis_options(analyze)
    analyze.add_argument("--json", action="store_true", help="Print the analysis as JSON.")

    accompany = commands.add_parser(
        "accompany", help="Write a bass and a drum MIDI file that follow the recording."
    )
    _add_analysis_options(accompany)
    accompany.add_argument("--output-dir", default="output", type=Path)
    accompany.add_argument("--style", choices=tuple(DRUM_STYLES), default="basic")
    accompany.add_argument("--seed", type=int, default=0)
    accompany.add_argument(
        "--pulse-bass",
        action="store_true",
        help="Play the bass on every beat instead of holding each chord.",
    )
    accompany.add_argument(
        "--constant-tempo",
        action="store_true",
        help=(
            "Write the files at the rounded average tempo from bar 1 instead of "
            "following every beat of the recording (for warped DAW clips)."
        ),
    )

    args = parser.parse_args(argv)
    try:
        analysis = analyze_audio(
            args.audio, beats_per_bar=args.beats_per_bar, tempo_hint=args.tempo_hint
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.command == "analyze":
        if args.json:
            print(json.dumps(analysis.to_dict(), indent=2))
        else:
            print(analysis.summary())
        return 0
    return _accompany(analysis, args)


def _add_analysis_options(parser: ArgumentParser) -> None:
    parser.add_argument("audio", type=Path, help="WAV, FLAC, OGG or MP3 file.")
    parser.add_argument(
        "--beats-per-bar",
        type=int,
        default=None,
        help="Fix the metre (quarter-note beats per bar) instead of estimating 4 vs 3.",
    )
    parser.add_argument(
        "--tempo-hint",
        type=float,
        default=None,
        help="Approximate BPM, when the detected tempo is half or double the real one.",
    )


def _accompany(analysis: MusicAnalysis, args: Namespace) -> int:
    try:
        accompaniment = generate_accompaniment(
            analysis, style=args.style, seed=args.seed, sustain_bass=not args.pulse_bass
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    files = export_accompaniment(
        accompaniment,
        analysis,
        args.output_dir,
        args.audio.stem,
        follow_recording=not args.constant_tempo,
    )

    print(analysis.summary())
    print()
    for warning in accompaniment.bass.report.warnings:
        print(f"warning: {warning}")
    if args.constant_tempo:
        print(
            f"Files start at bar 1 at {accompaniment.bass.request.bpm} BPM; align them "
            f"to the recording's first downbeat at "
            f"{analysis.grid.first_downbeat_seconds:.3f} s."
        )
    else:
        print("Files follow the recording's beats: start them together with the audio.")
    for path in (files.bass, files.drums, files.analysis):
        print(f"Written: {path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
