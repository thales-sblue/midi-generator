"""Source-independent musical understanding of a recording or clip.

``MusicAnalysis`` is what the engine knows about a piece before it generates
anything for it: where the beats and bars fall in time, the probable metre and
key, and the chord heard over each stretch. It is pure data with no audio or
MIDI library behind it, so an audio analyzer today and a MIDI clip analyzer
later can both produce it and feed the same generators.

Every estimate that comes from a signal carries a ``confidence`` in ``0..1``.
Those values are ordinal heuristics for ranking and for warning a human, not
calibrated probabilities.

Time is kept in two units. Seconds locate things in the source recording; beats
count quarter notes from the first downbeat (beat ``0.0`` is the downbeat of
bar 1, negative beats are a pickup). :class:`BeatGrid` converts between them
beat by beat, so a performance whose tempo drifts still maps onto the right
bar.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, floor
from typing import Any

from .music_theory import PITCH_CLASS_NAMES, ROOT_NOTES, SCALE_INTERVALS
from .time_signature import TimeSignature

MUSIC_ANALYSIS_SCHEMA_VERSION = 1
CHORD_QUALITIES = ("major", "minor")
NO_CHORD = "N"

# Largest value a MIDI set_tempo meta message can carry.
_MAX_MICROSECONDS_PER_BEAT = 0xFFFFFF


def _check_confidence(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number between 0 and 1.")
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field} must be between 0 and 1, got {value}.")


@dataclass(frozen=True)
class BeatGrid:
    """Beat positions of a recording and where its bars start.

    ``beat_times`` are strictly increasing seconds, one per quarter-note beat.
    ``first_downbeat_index`` points at the beat that opens bar 1; beats before
    it are a pickup. Bars are ``beats_per_bar`` beats long, and a bar only
    counts as complete when the beat that opens the next bar is also known.
    """

    beat_times: tuple[float, ...]
    first_downbeat_index: int
    beats_per_bar: int

    def __post_init__(self) -> None:
        if not isinstance(self.beat_times, tuple) or len(self.beat_times) < 2:
            raise ValueError("A beat grid needs at least two beat times.")
        if any(
            later <= earlier
            for earlier, later in zip(self.beat_times, self.beat_times[1:])
        ):
            raise ValueError("Beat times must be strictly increasing.")
        if self.beat_times[0] < 0:
            raise ValueError("Beat times must not be negative.")
        if not isinstance(self.beats_per_bar, int) or self.beats_per_bar < 1:
            raise ValueError("beats_per_bar must be a positive integer.")
        if not 0 <= self.first_downbeat_index < len(self.beat_times):
            raise ValueError("first_downbeat_index must point at a beat.")

    @property
    def tempo_bpm(self) -> float:
        """Average tempo over the whole grid (first to last beat).

        Averaging the span rather than taking a median interval keeps the
        figure unbiased when beat times are quantised to analysis frames.
        """
        span = self.beat_times[-1] - self.beat_times[0]
        return 60.0 * (len(self.beat_times) - 1) / span

    @property
    def first_downbeat_seconds(self) -> float:
        return self.beat_times[self.first_downbeat_index]

    @property
    def bar_count(self) -> int:
        """Complete bars from the first downbeat that the grid fully covers."""
        beats_after = len(self.beat_times) - 1 - self.first_downbeat_index
        return beats_after // self.beats_per_bar

    def seconds_to_beat(self, seconds: float) -> float:
        """Beat position of ``seconds``, interpolated between detected beats.

        Outside the grid the nearest edge interval is extended, so a time just
        before the first beat or after the last one still maps sensibly.
        """
        times = self.beat_times
        index = bisect_right(times, seconds) - 1
        index = min(max(index, 0), len(times) - 2)
        start, end = times[index], times[index + 1]
        position = index + (seconds - start) / (end - start)
        return position - self.first_downbeat_index

    def beat_to_seconds(self, beat: float) -> float:
        """Inverse of :meth:`seconds_to_beat`."""
        position = beat + self.first_downbeat_index
        times = self.beat_times
        index = min(max(floor(position), 0), len(times) - 2)
        start, end = times[index], times[index + 1]
        return start + (position - index) * (end - start)

    def beat_to_bar(self, beat: float) -> tuple[int, float]:
        """``(bar_number, beat_in_bar)`` for a beat position.

        Bar numbers start at 1 on the first downbeat; a pickup falls in bar 0
        or lower. ``beat_in_bar`` counts from 0.
        """
        bar_index, beat_in_bar = divmod(beat, self.beats_per_bar)
        return int(bar_index) + 1, beat_in_bar

    def bar_bounds_seconds(self, bar_number: int) -> tuple[float, float]:
        """Start and end seconds of a complete bar (1-based)."""
        if not 1 <= bar_number <= self.bar_count:
            raise ValueError(
                f"Bar {bar_number} is outside the {self.bar_count} complete bars."
            )
        start_index = self.first_downbeat_index + (bar_number - 1) * self.beats_per_bar
        return (
            self.beat_times[start_index],
            self.beat_times[start_index + self.beats_per_bar],
        )


@dataclass(frozen=True)
class KeyEstimate:
    """Most probable key, plus the reading it was preferred over.

    ``alternative`` names the runner-up (usually the relative key, which shares
    every pitch class) so a caller can see how close the call was.
    """

    root_note: str
    scale: str
    confidence: float
    alternative: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.root_note, str) or self.root_note.upper() not in ROOT_NOTES:
            raise ValueError("root_note must be one of C, C#, Db, D, etc.")
        if not isinstance(self.scale, str) or self.scale not in SCALE_INTERVALS:
            raise ValueError(f"scale must be one of: {', '.join(SCALE_INTERVALS)}.")
        _check_confidence(self.confidence, "Key confidence")

    @property
    def name(self) -> str:
        return f"{self.root_note} {self.scale}"


@dataclass(frozen=True)
class ChordSegment:
    """One chord heard from ``start_seconds`` to ``end_seconds``.

    ``root_note`` and ``quality`` are both ``None`` for a no-chord stretch
    (silence or material that matches no chord template).
    """

    start_seconds: float
    end_seconds: float
    root_note: str | None
    quality: str | None
    confidence: float

    def __post_init__(self) -> None:
        if not 0 <= self.start_seconds < self.end_seconds:
            raise ValueError("A chord segment must have 0 <= start < end.")
        if (self.root_note is None) != (self.quality is None):
            raise ValueError("root_note and quality must both be set or both be None.")
        if self.root_note is not None and self.root_note not in PITCH_CLASS_NAMES:
            raise ValueError(
                f"Chord root must be one of {', '.join(PITCH_CLASS_NAMES)}."
            )
        if self.quality is not None and self.quality not in CHORD_QUALITIES:
            raise ValueError(f"Chord quality must be one of {', '.join(CHORD_QUALITIES)}.")
        _check_confidence(self.confidence, "Chord confidence")

    @property
    def is_chord(self) -> bool:
        return self.root_note is not None

    @property
    def root_pitch_class(self) -> int | None:
        return None if self.root_note is None else ROOT_NOTES[self.root_note]

    @property
    def symbol(self) -> str:
        """Lead-sheet symbol such as ``Am`` or ``F``; ``N`` for no chord."""
        if self.root_note is None:
            return NO_CHORD
        return self.root_note + ("m" if self.quality == "minor" else "")


@dataclass(frozen=True)
class Measure:
    """What one bar of the piece holds.

    ``chord`` is the chord covering most of the bar; ``chords`` lists every
    chord that sounds for at least half a beat in it, in time order, so a bar
    with a mid-bar change is visible. ``energy`` is the bar's loudness relative
    to the loudest bar (``0..1``).
    """

    number: int
    start_seconds: float
    end_seconds: float
    chord: str
    chords: tuple[str, ...]
    energy: float

    def __post_init__(self) -> None:
        if not isinstance(self.number, int) or self.number < 1:
            raise ValueError("Measure numbers start at 1.")
        if not self.start_seconds < self.end_seconds:
            raise ValueError("A measure must end after it starts.")
        _check_confidence(self.energy, "Measure energy")


@dataclass(frozen=True)
class TempoChange:
    """A MIDI tempo event: from ``tick`` on, a beat lasts this many µs."""

    tick: int
    microseconds_per_beat: int


@dataclass(frozen=True)
class MidiTempoMap:
    """How to lay a plan's ticks onto the timeline of the source recording.

    ``lead_in_ticks`` of silence come first, timed so the plan's tick 0 lands
    on the recording's first downbeat; ``changes`` then give every beat the
    duration it actually had in the recording. A MIDI file written with this
    map and started together with the recording stays on its beats.
    """

    lead_in_ticks: int
    changes: tuple[TempoChange, ...]


@dataclass(frozen=True)
class MusicAnalysis:
    """Timeline, metre, key and harmony of a piece, independent of its source."""

    source: str
    duration_seconds: float
    grid: BeatGrid
    detected_beats: tuple[float, ...]
    tempo_confidence: float
    meter_confidence: float
    key: KeyEstimate
    chords: tuple[ChordSegment, ...]
    measures: tuple[Measure, ...]

    def __post_init__(self) -> None:
        if not self.duration_seconds > 0:
            raise ValueError("duration_seconds must be positive.")
        _check_confidence(self.tempo_confidence, "Tempo confidence")
        _check_confidence(self.meter_confidence, "Meter confidence")
        if len(self.measures) != self.grid.bar_count:
            raise ValueError("There must be one measure per complete bar of the grid.")

    @property
    def tempo_bpm(self) -> float:
        return self.grid.tempo_bpm

    @property
    def time_signature(self) -> TimeSignature:
        """Beats are quarter notes, so the metre is ``beats_per_bar/4``."""
        return TimeSignature(self.grid.beats_per_bar, 4)

    @property
    def bar_count(self) -> int:
        return self.grid.bar_count

    def progression(self) -> tuple[str, ...]:
        """The main chord of every bar, in order."""
        return tuple(measure.chord for measure in self.measures)

    def summary(self) -> str:
        """Short human-readable report of the analysis."""
        lines = [
            f"Tempo: {self.tempo_bpm:.1f} BPM (confidence {self.tempo_confidence:.2f})",
            f"Time signature: {self.time_signature} "
            f"(confidence {self.meter_confidence:.2f})",
            f"First downbeat: {self.grid.first_downbeat_seconds:.3f} s",
            f"Key: {self.key.name} (confidence {self.key.confidence:.2f}"
            + (f", alternative {self.key.alternative})" if self.key.alternative else ")"),
            "",
        ]
        for measure in self.measures:
            extra = ""
            if len(measure.chords) > 1:
                extra = f"  ({' -> '.join(measure.chords)})"
            lines.append(f"Bar {measure.number}: {measure.chord}{extra}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dictionary under its own versioned schema."""
        return {
            "schema": "music_analysis",
            "schema_version": MUSIC_ANALYSIS_SCHEMA_VERSION,
            "source": self.source,
            "duration_seconds": round(self.duration_seconds, 4),
            "tempo": round(self.tempo_bpm, 2),
            "tempo_confidence": round(self.tempo_confidence, 3),
            "time_signature": str(self.time_signature),
            "meter_confidence": round(self.meter_confidence, 3),
            "first_downbeat_seconds": round(self.grid.first_downbeat_seconds, 4),
            "beats": [round(value, 4) for value in self.grid.beat_times],
            "detected_beats": [round(value, 4) for value in self.detected_beats],
            "downbeats": [
                round(self.grid.bar_bounds_seconds(number)[0], 4)
                for number in range(1, self.bar_count + 1)
            ],
            "key": {
                "key": self.key.root_note,
                "mode": self.key.scale,
                "confidence": round(self.key.confidence, 3),
                "alternative": self.key.alternative,
            },
            "chords": [
                {
                    "start": round(segment.start_seconds, 4),
                    "end": round(segment.end_seconds, 4),
                    "chord": segment.symbol,
                    "confidence": round(segment.confidence, 3),
                }
                for segment in self.chords
            ],
            "measures": [
                {
                    "number": measure.number,
                    "start": round(measure.start_seconds, 4),
                    "end": round(measure.end_seconds, 4),
                    "chord": measure.chord,
                    "chords": list(measure.chords),
                    "energy": round(measure.energy, 3),
                }
                for measure in self.measures
            ],
        }


def build_measures(
    grid: BeatGrid,
    chords: Sequence[ChordSegment],
    energies: Sequence[float],
) -> tuple[Measure, ...]:
    """Assign the chord timeline to the grid's complete bars.

    A bar's main chord is the one overlapping it longest (earliest wins a tie;
    ``N`` when nothing overlaps). Chords overlapping it by at least half a beat
    are listed in time order. ``energies`` gives one ``0..1`` value per bar.
    """
    if len(energies) != grid.bar_count:
        raise ValueError("energies must hold one value per complete bar.")
    measures = []
    for number in range(1, grid.bar_count + 1):
        start, end = grid.bar_bounds_seconds(number)
        beat_seconds = (end - start) / grid.beats_per_bar
        overlaps: dict[str, float] = {}
        order: list[str] = []
        for segment in chords:
            overlap = min(end, segment.end_seconds) - max(start, segment.start_seconds)
            if overlap <= 0:
                continue
            if segment.symbol not in overlaps:
                order.append(segment.symbol)
                overlaps[segment.symbol] = 0.0
            overlaps[segment.symbol] += overlap
        main = max(order, key=lambda symbol: overlaps[symbol]) if order else NO_CHORD
        listed = tuple(
            symbol for symbol in order if overlaps[symbol] >= beat_seconds / 2
        ) or (main,)
        measures.append(
            Measure(
                number=number,
                start_seconds=start,
                end_seconds=end,
                chord=main,
                chords=listed,
                energy=energies[number - 1],
            )
        )
    return tuple(measures)


def tempo_map_for_grid(
    grid: BeatGrid, *, bars: int, ticks_per_beat: int
) -> MidiTempoMap:
    """Tempo map that puts ``bars`` bars of plan ticks onto ``grid``'s beats.

    The lead-in is a whole number of bars (so bar lines in the MIDI file stay
    on bar lines of the song) stretched to last exactly until the first
    downbeat; it is empty when the recording starts on the downbeat.
    """
    if not 1 <= bars <= grid.bar_count:
        raise ValueError(f"bars must be between 1 and {grid.bar_count}.")
    per_bar = grid.beats_per_bar
    changes: list[TempoChange] = []

    lead_seconds = grid.first_downbeat_seconds
    lead_in_ticks = 0
    if lead_seconds >= 0.0005:
        max_bar_seconds = per_bar * _MAX_MICROSECONDS_PER_BEAT / 1_000_000
        lead_bars = max(1, ceil(lead_seconds / max_bar_seconds))
        lead_in_ticks = lead_bars * per_bar * ticks_per_beat
        changes.append(
            TempoChange(0, round(lead_seconds * 1_000_000 / (lead_bars * per_bar)))
        )

    first = grid.first_downbeat_index
    for offset in range(bars * per_bar):
        index = first + offset
        duration = grid.beat_times[index + 1] - grid.beat_times[index]
        microseconds = round(duration * 1_000_000)
        if not 1 <= microseconds <= _MAX_MICROSECONDS_PER_BEAT:
            raise ValueError("A beat interval does not fit a MIDI tempo event.")
        if changes and changes[-1].microseconds_per_beat == microseconds:
            continue
        changes.append(
            TempoChange(lead_in_ticks + offset * ticks_per_beat, microseconds)
        )
    return MidiTempoMap(lead_in_ticks=lead_in_ticks, changes=tuple(changes))
