"""Diagnostics and installation helpers for the Ableton bridge."""

from argparse import ArgumentParser
from pathlib import Path

from .client import AbletonClient
from .config import DEFAULT_HOST, configured_port
from .errors import AbletonError
from .installer import install_remote_script


def doctor() -> int:
    port = configured_port()
    print(f"Ableton bridge endpoint: {DEFAULT_HOST}:{port}")
    try:
        result = AbletonClient(port=port).ping()
    except (AbletonError, ValueError) as error:
        print("Ableton bridge: unavailable")
        print(f"Reason: {error}")
        return 1
    print("Ableton bridge: connected")
    print(f"Live: {result.get('application', 'detected')}")
    if result.get("version"):
        print(f"Version: {result['version']}")
    print(f"Bridge: {result.get('bridge', 'MidiGeneratorBridge')}")
    print("Protocol: compatible")
    return 0


BEATS_PER_BAR = 4


def transport(action: str, bars: list[int], from_bar: int | None) -> int:
    client = AbletonClient()
    try:
        if action == "loop":
            first, last = bars
            if first < 1 or last < first:
                print("Loop bars must satisfy 1 <= first <= last.")
                return 2
            state = client.set_loop(
                (first - 1) * BEATS_PER_BAR, (last - first + 1) * BEATS_PER_BAR
            )
        elif action == "play":
            start = None if from_bar is None else (from_bar - 1) * BEATS_PER_BAR
            state = client.play(start)
        elif action == "stop":
            state = client.stop()
        else:
            state = client.get_transport()
    except (AbletonError, ValueError) as error:
        print(f"Ableton bridge: {error}")
        return 1
    first_bar = state["loop_start_beats"] / BEATS_PER_BAR + 1
    last_bar = first_bar + state["loop_length_beats"] / BEATS_PER_BAR - 1
    print(f"Playing: {'yes' if state['is_playing'] else 'no'}")
    print(f"Loop: {'on' if state['loop'] else 'off'}, bars {first_bar:g}-{last_bar:g}")
    print(f"Position: bar {state['current_beats'] / BEATS_PER_BAR + 1:g}")
    return 0


def main() -> None:
    parser = ArgumentParser(description="Ableton Live bridge utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check the local Ableton bridge.")
    install = subparsers.add_parser("install-script", help="Copy the Remote Script.")
    install.add_argument("--destination", type=Path)
    transport_parser = subparsers.add_parser(
        "transport", help="Play, stop or loop the Arrangement (4/4 bars, 1-based)."
    )
    transport_parser.add_argument("action", choices=["status", "play", "stop", "loop"])
    transport_parser.add_argument(
        "bars", nargs="*", type=int, help="loop: first and last bar, inclusive."
    )
    transport_parser.add_argument("--from-bar", type=int)
    args = parser.parse_args()
    if args.command == "doctor":
        raise SystemExit(doctor())
    if args.command == "transport":
        if (args.action == "loop") != (len(args.bars) == 2):
            parser.error("loop takes exactly two bars; other actions take none.")
        if args.from_bar is not None and args.from_bar < 1:
            parser.error("--from-bar must be 1 or greater.")
        raise SystemExit(transport(args.action, args.bars, args.from_bar))
    destination = install_remote_script(args.destination)
    print(f"Remote Script copied to: {destination}")
    print("Restart Live, then select MidiGeneratorBridge as a Control Surface.")


if __name__ == "__main__":
    main()
