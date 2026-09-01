"""Small immutable music-theory tables shared by composition and transformations."""

ROOT_NOTES = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
    "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
    "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}

# Seven-note scales as semitone offsets from the tonic. "major" and "minor"
# (natural minor) stay first so their historical tie-break order in scale
# ranking is unchanged; "major" is the Ionian mode and "minor" the Aeolian.
SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
}

PITCH_CLASS_NAMES = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)


def scale_pitch_classes(root_note: str, scale: str) -> frozenset[int]:
    """Return the 0..11 pitch classes of a named scale rooted on a named note."""
    if not isinstance(root_note, str) or root_note.upper() not in ROOT_NOTES:
        raise ValueError("root_note must be one of C, C#, Db, D, etc.")
    if not isinstance(scale, str) or scale.lower() not in SCALE_INTERVALS:
        raise ValueError(f"scale must be one of: {', '.join(SCALE_INTERVALS)}.")
    root = ROOT_NOTES[root_note.upper()]
    return frozenset(
        (root + interval) % 12 for interval in SCALE_INTERVALS[scale.lower()]
    )


def scale_pitches(root_note: str, scale: str) -> tuple[int, ...]:
    """Return every MIDI pitch 0..127 that belongs to the given scale, ascending."""
    allowed = scale_pitch_classes(root_note, scale)
    return tuple(pitch for pitch in range(128) if pitch % 12 in allowed)


def nearest_scale_pitch(pitch: int, pitch_classes: frozenset[int] | set[int]) -> int:
    """Return the closest MIDI pitch whose class is allowed; ties resolve downward.

    Resolving equidistant choices downward keeps the mapping deterministic and
    avoids an unintended upward drift when a whole line is snapped to a scale.
    """
    for distance in range(13):
        lower = pitch - distance
        if lower >= 0 and lower % 12 in pitch_classes:
            return lower
        upper = pitch + distance
        if upper <= 127 and upper % 12 in pitch_classes:
            return upper
    raise AssertionError("Every scale must contain a reachable MIDI pitch.")
