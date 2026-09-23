"""Tempo, beat positions, metre and first downbeat of a recording.

Beat tracking is librosa's dynamic-programming tracker (Ellis 2007) over an
onset-strength envelope. It finds *where* beats fall, not only a global BPM;
the rest of this module turns those positions into a regular grid and decides
which beat opens bar 1.

Downbeats are inferred, not detected by a trained model: in accompaniment
material chords tend to change, and strums tend to be accented, on the first
beat of a bar. :func:`estimate_meter` scores every (beats-per-bar, phase)
hypothesis by how much harmonic change and accent land on its would-be
downbeats compared to the other beats.
"""

from dataclasses import dataclass

import librosa
import numpy as np

from .loader import AudioSignal

HOP_LENGTH = 512
# Finer hop used only to place beats on the attacks they belong to.
_ONSET_HOP_LENGTH = 128
# How far a tracked beat may move to reach its attack.
_SNAP_WINDOW_SECONDS = 0.07
# Onsets this close together belong to one strum.
_STRUM_SECONDS = 0.05
METER_CANDIDATES = (4, 3)
# A gap this many median periods wide means the tracker skipped beats.
_GAP_FACTOR = 1.5
# Weight of accent contrast relative to harmonic-change contrast.
_ACCENT_WEIGHT = 0.5


@dataclass(frozen=True, eq=False)
class BeatDetection:
    """Raw tracker output plus the onset envelope it was computed from."""

    beat_times: np.ndarray
    onset_envelope: np.ndarray
    hop_length: int


@dataclass(frozen=True)
class MeterEstimate:
    beats_per_bar: int
    first_downbeat_index: int
    confidence: float


def detect_beats(
    signal: AudioSignal, *, tempo_hint: float | None = None
) -> BeatDetection:
    """Track beats, optionally at a tempo given by the caller.

    Without a hint the tracker estimates the tempo itself, with a prior
    centred on 120 BPM; like every beat tracker it can then lock onto half or
    double the felt tempo, most often for slow songs (under ~70 BPM) that it
    reads in double time. ``tempo_hint`` (approximate BPM) replaces that
    estimate; the tracker still places every beat on the audio, so the hint
    only has to pick the right tempo octave.
    """
    envelope = librosa.onset.onset_strength(
        y=signal.samples, sr=signal.sample_rate, hop_length=HOP_LENGTH
    )
    kwargs = {} if tempo_hint is None else {"bpm": float(tempo_hint)}
    _, beat_times = librosa.beat.beat_track(
        onset_envelope=envelope,
        sr=signal.sample_rate,
        hop_length=HOP_LENGTH,
        units="time",
        **kwargs,
    )
    attacks = attack_times(signal)
    beats = snap_to_onsets(np.asarray(beat_times, dtype=float), attacks)
    return BeatDetection(
        beat_times=extend_backward(beats, attacks),
        onset_envelope=envelope,
        hop_length=HOP_LENGTH,
    )


def attack_times(signal: AudioSignal) -> np.ndarray:
    """Start of every detected attack, in seconds.

    Onsets are picked on a finer grid than beat tracking uses and backtracked
    to the energy minimum before each onset peak, i.e. to where the attack
    begins rather than where it is loudest.
    """
    onsets = librosa.onset.onset_detect(
        y=signal.samples,
        sr=signal.sample_rate,
        hop_length=_ONSET_HOP_LENGTH,
        backtrack=True,
        units="time",
    )
    return merge_strums(onsets)


def merge_strums(onsets: np.ndarray) -> np.ndarray:
    """Collapse onsets closer than 50 ms into the first one.

    A strum crosses the strings over a few tens of milliseconds and the onset
    detector can fire more than once on it; the strum begins at its first
    onset.
    """
    merged: list[float] = []
    for onset in np.sort(np.asarray(onsets, dtype=float)):
        if not merged or onset - merged[-1] >= _STRUM_SECONDS:
            merged.append(float(onset))
    return np.asarray(merged)


def snap_to_onsets(beat_times: np.ndarray, attacks: np.ndarray) -> np.ndarray:
    """Move tracked beats onto the attacks they belong to.

    The tracker reports beats on a 23 ms frame grid and on the peak of the
    onset envelope, which trails the audible attack by a roughly constant lag.
    The median offset between beats and their nearest attack (within 70 ms)
    estimates that lag and is applied to every beat; a beat then snaps to an
    attack within 35 ms of its corrected position. A beat with no attack
    there (a soft repeated strum the onset detector missed) is spaced evenly
    between the nearest snapped beats on either side, which are more reliable
    than the tracker's own frame-quantised guess; at the edges it keeps the
    corrected position.
    """
    if beat_times.size == 0 or attacks.size == 0:
        return beat_times
    offsets = _nearest(attacks, beat_times) - beat_times
    matched = np.abs(offsets) <= _SNAP_WINDOW_SECONDS
    if not matched.any():
        return beat_times
    corrected = beat_times + float(np.median(offsets[matched]))
    nearest = _nearest(attacks, corrected)
    anchored = np.abs(nearest - corrected) <= _SNAP_WINDOW_SECONDS / 2
    snapped = np.where(anchored, nearest, corrected)
    anchors = np.flatnonzero(anchored)
    if anchors.size:
        positions = np.arange(snapped.size)
        inner = (positions > anchors[0]) & (positions < anchors[-1])
        loose = np.flatnonzero(~anchored & inner)
        snapped[loose] = np.interp(loose, anchors, snapped[anchors])
    # Two beats must never collapse onto one attack, nor start before 0.
    for candidate in (snapped, corrected):
        if candidate[0] >= 0 and np.all(np.diff(candidate) > 0):
            return candidate
    return beat_times


def extend_backward(beat_times: np.ndarray, attacks: np.ndarray) -> np.ndarray:
    """Recover leading beats the tracker trimmed.

    The tracker drops weak beats at the start, which in a slow song can be
    the whole first strum. While an attack sits within 35 ms of where the
    previous beat would fall (one median period earlier), that attack is
    prepended as a beat. Nothing is ever added over silence.
    """
    if beat_times.size < 2 or attacks.size == 0:
        return beat_times
    period = float(np.median(np.diff(beat_times)))
    beats = list(beat_times)
    while True:
        expected = beats[0] - period
        if expected < -_SNAP_WINDOW_SECONDS / 2:
            break
        candidate = float(_nearest(attacks, np.array([expected]))[0])
        if abs(candidate - expected) > _SNAP_WINDOW_SECONDS / 2 or candidate >= beats[0]:
            break
        beats.insert(0, candidate)
    return np.asarray(beats)


def _nearest(sorted_values: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """The element of ``sorted_values`` closest to each target."""
    if sorted_values.size == 1:
        return np.full_like(targets, sorted_values[0])
    positions = np.clip(np.searchsorted(sorted_values, targets), 1, sorted_values.size - 1)
    before, after = sorted_values[positions - 1], sorted_values[positions]
    return np.where(targets - before <= after - targets, before, after)


def regularize_beats(beat_times: np.ndarray, duration_seconds: float) -> np.ndarray:
    """Fill skipped beats and extend the grid to the end of the recording.

    Any interval wider than 1.5 median periods is split evenly into the number
    of beats it most likely held. After the last detected beat, beats continue
    at the mean period of the filled grid while they still fall inside the
    recording, so the final bar can be closed.
    """
    beats = np.asarray(beat_times, dtype=float)
    if beats.size < 2:
        raise ValueError("At least two beats are needed to build a beat grid.")
    period = float(np.median(np.diff(beats)))
    filled = [float(beats[0])]
    for later in beats[1:]:
        previous = filled[-1]
        gap = float(later) - previous
        steps = max(1, round(gap / period)) if gap > _GAP_FACTOR * period else 1
        filled.extend(previous + gap * step / steps for step in range(1, steps + 1))
    mean_period = (filled[-1] - filled[0]) / (len(filled) - 1)
    while filled[-1] + mean_period <= duration_seconds:
        filled.append(filled[-1] + mean_period)
    return np.asarray(filled)


def tempo_confidence(beat_times: np.ndarray) -> float:
    """Regularity of the detected beat intervals, ``1`` for a perfect grid.

    It falls with the coefficient of variation of the intervals and reaches 0
    at 25 % variation. This measures steadiness, not whether the tracker chose
    the felt tempo rather than its half or double.
    """
    intervals = np.diff(np.asarray(beat_times, dtype=float))
    if intervals.size < 2:
        return 0.0
    variation = float(np.std(intervals) / np.median(intervals))
    return float(np.clip(1.0 - 4.0 * variation, 0.0, 1.0))


def beat_accents(detection: BeatDetection, grid: np.ndarray, sample_rate: int) -> np.ndarray:
    """Onset strength at every grid beat.

    Grid beats sit on attacks and the onset envelope peaks just after them, so
    each beat takes the envelope's peak from one frame before it to 100 ms
    after it.
    """
    envelope = detection.onset_envelope
    frames = librosa.time_to_frames(grid, sr=sample_rate, hop_length=detection.hop_length)
    reach = max(1, int(round(0.1 * sample_rate / detection.hop_length)))
    return np.array(
        [
            float(envelope[max(0, frame - 1) : frame + reach + 1].max(initial=0.0))
            for frame in frames
        ]
    )


def harmonic_change(beat_chroma: np.ndarray) -> np.ndarray:
    """Cosine distance between each beat's chroma and the previous beat's.

    Beat 0 has no predecessor and gets 0.
    """
    norms = np.linalg.norm(beat_chroma, axis=0)
    unit = beat_chroma / np.maximum(norms, 1e-9)
    change = np.zeros(beat_chroma.shape[1])
    change[1:] = 1.0 - np.sum(unit[:, 1:] * unit[:, :-1], axis=0)
    change[norms < 1e-9] = 0.0
    return change


def estimate_meter(
    change: np.ndarray,
    accents: np.ndarray,
    *,
    candidates: tuple[int, ...] = METER_CANDIDATES,
) -> MeterEstimate:
    """Pick beats-per-bar and the index of the first downbeat.

    Every ``(beats_per_bar, phase)`` hypothesis is scored by the relative
    contrast between its downbeats and its other beats, in harmonic change plus
    half-weighted accent. Confidence is the margin of the winner over the best
    competing hypothesis (another phase, or another metre when several are
    candidates), relative to the winner's own score.
    """
    beat_count = len(change)
    if beat_count != len(accents):
        raise ValueError("change and accents must describe the same beats.")
    if not candidates or any(value < 2 for value in candidates):
        raise ValueError("Metre candidates must be at least two beats per bar.")
    if beat_count < 2 * max(candidates):
        raise ValueError("Too few beats to estimate the metre.")

    indices = np.arange(beat_count)
    scores: dict[tuple[int, int], float] = {}
    for per_bar in candidates:
        for phase in range(per_bar):
            downbeats = (indices - phase) % per_bar == 0
            scores[(per_bar, phase)] = _contrast(change[1:], downbeats[1:]) + (
                _ACCENT_WEIGHT * _contrast(accents, downbeats)
            )
    (per_bar, phase), best = max(scores.items(), key=lambda item: item[1])
    rivals = [score for key, score in scores.items() if key != (per_bar, phase)]
    runner_up = max(rivals) if rivals else 0.0
    confidence = 0.0 if best <= 0 else float(np.clip((best - runner_up) / best, 0.0, 1.0))
    return MeterEstimate(per_bar, phase, confidence)


def _contrast(values: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any() or mask.all():
        return 0.0
    scale = float(np.mean(values))
    if scale <= 1e-9:
        return 0.0
    return (float(np.mean(values[mask])) - float(np.mean(values[~mask]))) / scale
