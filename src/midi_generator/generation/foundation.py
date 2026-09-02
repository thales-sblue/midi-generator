"""Window-by-window harmonic foundation shared by the role-aware generators.

The bass-line and chord-bed generators both read the same thing from a
reference clip: its lowest sounding pitch per metric window, snapped into the
caller's scale and optionally anchored in a register. This module owns that
step so each generator only has to decide how to voice it.
"""

from collections.abc import Callable
from dataclasses import dataclass

from midi_generator.analysis import bass_line_pitches
from midi_generator.domain import (
    MelodyRequest,
    nearest_scale_pitch,
    scale_pitch_classes,
)
from midi_generator.domain.music_theory import ROOT_NOTES, SCALE_INTERVALS
from midi_generator.transformations import EditableMidiClip

from .melody import TICKS_PER_BEAT


@dataclass(frozen=True)
class FoundationLine:
    """A reference clip's bass line, snapped to a scale and cut into windows.

    ``pitches`` holds one entry per metric window, in order: the snapped
    foundation pitch of that window with ``octave_offset`` already applied, or
    ``None`` when the window is silent.
    """

    pitches: tuple[int | None, ...]
    segment_ticks: int
    total_ticks: int
    octave_offset: int

    @property
    def sounding_count(self) -> int:
        """Number of windows that carry a foundation pitch."""
        return sum(pitch is not None for pitch in self.pitches)

    def window_bounds(self, index: int) -> tuple[int, int]:
        """Start and end ticks of window ``index``, clamped to the clip end."""
        start = index * self.segment_ticks
        return start, min(start + self.segment_ticks, self.total_ticks)


def build_foundation_line(
    request: MelodyRequest,
    reference: EditableMidiClip,
    *,
    segment_beats: int = 1,
    octave: int | None = None,
) -> FoundationLine:
    """Read ``reference``'s foundation into the scale and register of ``request``.

    ``analysis.bass_line_pitches`` supplies the lowest sounding pitch of every
    ``segment_beats``-beat window; each one is snapped to the nearest pitch of
    the request's scale, ties downward. The line spans exactly the reference
    clip, so ``request.bars`` and ``request.time_signature`` must describe that
    same length.

    ``octave`` is ``None`` by default, which keeps whatever register the
    reference's lowest notes sat in. Given an integer MIDI octave (``C-1`` is
    octave ``-1``, middle C is octave ``4``), a single whole-octave offset moves
    the lowest snapped pitch into that octave and applies to every window, so
    the contour and every interval survive untouched.

    The function is pure and draws no randomness.
    """
    request.validate()
    if request.root_note.upper() not in ROOT_NOTES:
        raise ValueError("Root note must be one of C, C#, Db, D, etc.")
    if request.scale.lower() not in SCALE_INTERVALS:
        raise ValueError(f"Scale must be one of: {', '.join(SCALE_INTERVALS)}.")
    if octave is not None and (
        not isinstance(octave, int)
        or isinstance(octave, bool)
        or not -1 <= octave <= 9
    ):
        raise ValueError("octave must be an integer between -1 and 9, or None.")
    reference.validate()

    total_ticks = request.bars * request.time_signature.bar_ticks(TICKS_PER_BEAT)
    if total_ticks != reference.length_ticks:
        raise ValueError(
            "Following a reference clip requires the request length to match "
            f"the reference clip length ({reference.length_ticks} ticks), got "
            f"{total_ticks}."
        )
    if all(note.mute for note in reference.notes):
        raise ValueError("Reference clip must contain at least one sounding note.")

    pitch_classes = scale_pitch_classes(request.root_note, request.scale)
    snapped = tuple(
        None if pitch is None else nearest_scale_pitch(pitch, pitch_classes)
        for pitch in bass_line_pitches(reference, segment_beats=segment_beats)
    )
    offset = _octave_offset([pitch for pitch in snapped if pitch is not None], octave)
    return FoundationLine(
        pitches=tuple(
            None if pitch is None else pitch + offset for pitch in snapped
        ),
        segment_ticks=segment_beats * reference.ticks_per_beat,
        total_ticks=total_ticks,
        octave_offset=offset,
    )


def voice_windows(
    line: FoundationLine,
    voicing: Callable[[int], tuple[int, ...]],
    *,
    sustain: bool,
) -> tuple[tuple[tuple[int, ...], int, int], ...]:
    """Voice every sounding window of ``line`` and tie repeats when sustaining.

    ``voicing`` turns one foundation pitch into the pitches sounding over that
    window — a single note for a bass line, a chord for a chord bed. The result
    is one ``(pitches, start_tick, end_tick)`` entry per emitted sonority, in
    time order. With ``sustain`` set, consecutive windows that voice to exactly
    the same pitches and touch end to end are merged into one longer entry, so
    a silent window always breaks the tie.
    """
    voiced: list[tuple[tuple[int, ...], int, int]] = []
    for index, pitch in enumerate(line.pitches):
        if pitch is None:
            continue
        pitches = voicing(pitch)
        start, end = line.window_bounds(index)
        if sustain and voiced and voiced[-1][0] == pitches and voiced[-1][2] == start:
            held_pitches, held_start, _ = voiced[-1]
            voiced[-1] = (held_pitches, held_start, end)
            continue
        voiced.append((pitches, start, end))
    return tuple(voiced)


def _octave_offset(snapped_line: list[int], octave: int | None) -> int:
    """Whole-octave transposition that anchors ``snapped_line``'s lowest note.

    Returns the semitone offset (a multiple of 12) that moves the lowest snapped
    pitch into the requested MIDI ``octave``; ``0`` when ``octave`` is ``None``
    or the line is empty. Raises when the shift would carry any note past 127.
    """
    if octave is None or not snapped_line:
        return 0
    floor_pitch = (octave + 1) * 12
    lowest = min(snapped_line)
    steps = -(-(floor_pitch - lowest) // 12)  # ceil division
    offset = 12 * steps
    if max(snapped_line) + offset > 127:
        raise ValueError(
            "The foundation does not fit at or above octave "
            f"{octave} without a note exceeding MIDI 127."
        )
    return offset
