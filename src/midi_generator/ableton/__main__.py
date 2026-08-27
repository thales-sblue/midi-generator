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


def main() -> None:
    parser = ArgumentParser(description="Ableton Live bridge utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Check the local Ableton bridge.")
    install = subparsers.add_parser("install-script", help="Copy the Remote Script.")
    install.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.command == "doctor":
        raise SystemExit(doctor())
    destination = install_remote_script(args.destination)
    print(f"Remote Script copied to: {destination}")
    print("Restart Live, then select MidiGeneratorBridge as a Control Surface.")


if __name__ == "__main__":
    main()
