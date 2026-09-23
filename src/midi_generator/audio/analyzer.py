"""Recording -> :class:`MusicAnalysis`: the engine's ear.

``analyze_audio`` chains the steps of this package and returns the same
source-independent model the generators consume. Every step is local and
offline; nothing is downloaded at analysis time.
"""

from pathlib import Path

import numpy as np

from midi_generator.domain import BeatGrid, MusicAnalysis, build_measures

from .harmony import (
    active_beats,
    beat_features,
    chord_segments,
    decode_chords,
    estimate_key,
)
from .loader import DEFAULT_SAMPLE_RATE, AudioSignal, load_audio
from .rhythm import (
    METER_CANDIDATES,
    beat_accents,
    detect_beats,
    estimate_meter,
    harmonic_change,
    regularize_beats,
    tempo_confidence,
)

MAX_BEATS_PER_BAR = 12


def analyze_audio(
    path: str | Path,
    *,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> MusicAnalysis:
    """Analyse a recording file. See :func:`analyze_signal`."""
    signal = load_audio(path, sample_rate=sample_rate)
    return analyze_signal(signal, beats_per_bar=beats_per_bar, tempo_hint=tempo_hint)


def analyze_signal(
    signal: AudioSignal,
    *,
    beats_per_bar: int | None = None,
    tempo_hint: float | None = None,
) -> MusicAnalysis:
    """Beats, metre, downbeat, chords, key and per-bar energy of ``signal``.

    ``beats_per_bar`` fixes the metre (quarter-note beats per bar) instead of
    choosing between 4 and 3; the first downbeat is still estimated.
    ``tempo_hint`` (BPM) steers the beat tracker away from half/double tempo.
    """
    if beats_per_bar is not None and (
        not isinstance(beats_per_bar, int)
        or isinstance(beats_per_bar, bool)
        or not 2 <= beats_per_bar <= MAX_BEATS_PER_BAR
    ):
        raise ValueError(
            f"beats_per_bar must be an integer between 2 and {MAX_BEATS_PER_BAR}."
        )
    if tempo_hint is not None and not 20 <= tempo_hint <= 400:
        raise ValueError("tempo_hint must be between 20 and 400 BPM.")

    detection = detect_beats(signal, tempo_hint=tempo_hint)
    if detection.beat_times.size < 2:
        raise ValueError("No steady beat was found in the recording.")
    grid = regularize_beats(detection.beat_times, signal.duration_seconds)

    features = beat_features(signal, grid)
    active = active_beats(features.rms)
    if not active.any():
        raise ValueError("The recording holds no audible beat.")
    # Drop the silent tail, keeping one beat after the last audible one to
    # close its bar.
    keep = min(len(grid), int(np.flatnonzero(active)[-1]) + 2)
    grid, features, active = grid[:keep], features[:keep], active[:keep]

    candidates = METER_CANDIDATES if beats_per_bar is None else (beats_per_bar,)
    if keep < 2 * max(candidates):
        raise ValueError("The recording is too short to find its bars.")
    meter = estimate_meter(
        harmonic_change(features.chroma),
        beat_accents(detection, grid, signal.sample_rate),
        candidates=candidates,
    )
    beat_grid = BeatGrid(
        beat_times=tuple(float(value) for value in grid),
        first_downbeat_index=meter.first_downbeat_index,
        beats_per_bar=meter.beats_per_bar,
    )
    if beat_grid.bar_count < 1:
        raise ValueError("The recording is too short to hold one complete bar.")

    states, confidence = decode_chords(features.chroma, active, features.bass)
    chords = chord_segments(states, confidence, grid, signal.duration_seconds)
    profile = (features.chroma[:, active] * features.rms[active]).sum(axis=1)
    key = estimate_key(profile, chords)

    measures = build_measures(beat_grid, chords, _bar_energies(beat_grid, features.rms))
    return MusicAnalysis(
        source=signal.source,
        duration_seconds=signal.duration_seconds,
        grid=beat_grid,
        detected_beats=tuple(float(value) for value in detection.beat_times),
        tempo_confidence=tempo_confidence(detection.beat_times),
        meter_confidence=meter.confidence,
        key=key,
        chords=chords,
        measures=measures,
    )


def _bar_energies(grid: BeatGrid, beat_rms: np.ndarray) -> list[float]:
    """Mean beat RMS of every complete bar, relative to the loudest bar."""
    per_bar = grid.beats_per_bar
    first = grid.first_downbeat_index
    means = [
        float(np.mean(beat_rms[first + bar * per_bar : first + (bar + 1) * per_bar]))
        for bar in range(grid.bar_count)
    ]
    loudest = max(means)
    return [round(value / loudest, 4) if loudest > 0 else 0.0 for value in means]
