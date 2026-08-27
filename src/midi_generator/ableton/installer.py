"""Safe copy-only installer for the Ableton Remote Script."""

import shutil
from pathlib import Path

SCRIPT_NAME = "MidiGeneratorBridge"


def default_remote_scripts_directory() -> Path:
    return Path.home() / "Documents" / "Ableton" / "User Library" / "Remote Scripts"


def bundled_script_directory() -> Path:
    return Path(__file__).parents[3] / "ableton_remote_script" / SCRIPT_NAME


def install_remote_script(destination_root: Path | None = None) -> Path:
    source = bundled_script_directory().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Bundled Remote Script not found: {source}")
    root = (destination_root or default_remote_scripts_directory()).resolve()
    destination = root / SCRIPT_NAME
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return destination
