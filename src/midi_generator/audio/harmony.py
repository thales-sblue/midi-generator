"""Beat-synchronous chroma, chord recognition and key estimation.

Chord recognition is the classic template-matching baseline of MIR
(Fujishima 1999; the approach behind librosa's own chord-recognition example):

1. constant-Q chroma of the harmonic part of the signal (HPSS removes most of
   the strum noise);
2. one median chroma vector per beat;
3. cosine similarity against the 24 major and minor triad templates, plus a
   constant score for "no chord", plus a small bonus when the chord's root is
   the strongest pitch class in the guitar's bass register (E2..D#3) — this
   breaks ties such as Fmaj7, which contains the whole of an A minor triad;
4. Viterbi smoothing (librosa) with a self-transition bias, so a chord is not
   abandoned for a single ambiguous beat.

It recognises major and minor triads only. Sevenths, suspensions and power
chords are read as the nearest triad (a power chord has no third, so its
quality is a coin toss and its confidence drops); inversions are read by root.
Chords are placed on beats, which is what accompaniment needs.

The key comes from correlating the whole piece's chroma with the
Krumhansl–Kessler key profiles, plus the share of chord time that is diatonic
to each candidate key. Relative keys (A minor / C major) share every
pitch class and are hard to tell apart from chroma alone, so between the best
key and its relative the chord timeline decides: the key whose tonic triad
opens the piece, closes it and is heard longest wins.
"""

from dataclasses import dataclass

import librosa
import numpy as np

from midi_generator.domain import ChordSegment, KeyEstimate
from midi_generator.domain.music_theory import PITCH_CLASS_NAMES, SCALE_INTERVALS

from .loader import AudioSignal
from .rhythm import HOP_LENGTH

CHORD_QUALITY_INTERVALS = {"major": (0, 4, 7), "minor": (0, 3, 7)}
# (root pitch class, quality) of each template, then one "no chord" state.
CHORD_LABELS = tuple(
    (root, quality) for quality in CHORD_QUALITY_INTERVALS for root in range(12)
)
NO_CHORD_STATE = len(CHORD_LABELS)
# Similarity a beat must beat for a triad to be preferred over "no chord".
_NO_CHORD_SCORE = 0.55
# Sharpness of the similarity -> probability softmax.
_SOFTMAX_SHARPNESS = 15.0
_SELF_TRANSITION = 0.6
# A beat quieter than this fraction of the loudest beat counts as silent.
SILENT_BEAT_RATIO = 0.08
# Bonus for a template whose root dominates the bass register; small enough
# that it only decides between chords the upper voices leave near-tied.
_BASS_ROOT_WEIGHT = 0.15
# The lowest octave of a guitar in standard tuning.
_BASS_REGISTER_FLOOR = "E2"

# Krumhansl & Kessler (1982) probe-tone profiles, tonic first.
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_TONIC_EVIDENCE_WEIGHT = 0.3
# Share of chroma energy a seven-note scale holds by chance (flat chroma).
_CHANCE_IN_SCALE = 7 / 12


def chord_templates() -> np.ndarray:
    """Unit-norm 12-bin templates, one row per entry of ``CHORD_LABELS``."""
    templates = np.zeros((len(CHORD_LABELS), 12))
    for row, (root, quality) in enumerate(CHORD_LABELS):
        for interval in CHORD_QUALITY_INTERVALS[quality]:
            templates[row, (root + interval) % 12] = 1.0
    return templates / np.linalg.norm(templates, axis=1, keepdims=True)


@dataclass(frozen=True, eq=False)
class BeatFeatures:
    """Per-beat harmony and loudness.

    ``chroma`` covers the full range and ``bass`` only the lowest guitar
    octave, both 12 x beats; ``rms`` holds one loudness value per beat.
    Slicing selects beats.
    """

    chroma: np.ndarray
    bass: np.ndarray
    rms: np.ndarray

    def __getitem__(self, beats: slice) -> "BeatFeatures":
        return BeatFeatures(self.chroma[:, beats], self.bass[:, beats], self.rms[beats])


def beat_features(signal: AudioSignal, grid: np.ndarray) -> BeatFeatures:
    """Median chroma, median bass chroma and mean RMS of every grid beat.

    Beat ``i`` spans ``grid[i]`` to ``grid[i + 1]``; the last one runs to the
    end of the recording.
    """
    harmonic = librosa.effects.harmonic(signal.samples)
    chroma = librosa.feature.chroma_cqt(
        y=harmonic, sr=signal.sample_rate, hop_length=HOP_LENGTH
    )
    bass = librosa.feature.chroma_cqt(
        y=harmonic,
        sr=signal.sample_rate,
        hop_length=HOP_LENGTH,
        fmin=librosa.note_to_hz(_BASS_REGISTER_FLOOR),
        n_octaves=1,
    )
    rms = librosa.feature.rms(y=signal.samples, hop_length=HOP_LENGTH)[0]
    frame_count = min(chroma.shape[1], bass.shape[1], rms.shape[0])
    bounds = librosa.time_to_frames(grid, sr=signal.sample_rate, hop_length=HOP_LENGTH)
    bounds = np.clip(np.append(bounds, frame_count), 0, frame_count)

    beat_chroma = np.zeros((12, len(grid)))
    beat_bass = np.zeros((12, len(grid)))
    beat_rms = np.zeros(len(grid))
    for index in range(len(grid)):
        start, end = bounds[index], max(bounds[index + 1], bounds[index] + 1)
        if start >= frame_count:
            continue
        beat_chroma[:, index] = np.median(chroma[:, start:end], axis=1)
        beat_bass[:, index] = np.median(bass[:, start:end], axis=1)
        beat_rms[index] = float(np.mean(rms[start:end]))
    return BeatFeatures(beat_chroma, beat_bass, beat_rms)


def active_beats(beat_rms: np.ndarray) -> np.ndarray:
    """Beats loud enough to carry harmony."""
    loudest = float(np.max(beat_rms)) if beat_rms.size else 0.0
    if loudest <= 0:
        return np.zeros(beat_rms.shape, dtype=bool)
    return beat_rms >= SILENT_BEAT_RATIO * loudest


def decode_chords(
    beat_chroma: np.ndarray,
    active: np.ndarray,
    bass: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Most likely chord state per beat and its (softmax) confidence.

    ``bass`` (12 x beats, optional) is the bass-register chroma; a template
    earns a bonus in proportion to how strongly its root sounds there,
    relative to the strongest bass pitch class of that beat.

    Returns state indices into ``CHORD_LABELS`` (``NO_CHORD_STATE`` for no
    chord) and a ``0..1`` confidence per beat. Silent beats are forced to no
    chord.
    """
    beat_count = beat_chroma.shape[1]
    norms = np.linalg.norm(beat_chroma, axis=0)
    unit = beat_chroma / np.maximum(norms, 1e-9)
    chord_scores = chord_templates() @ unit
    if bass is not None:
        peaks = np.maximum(bass.max(axis=0, keepdims=True), 1e-9)
        roots = np.array([root for root, _ in CHORD_LABELS])
        chord_scores = chord_scores + _BASS_ROOT_WEIGHT * (bass / peaks)[roots]
    similarity = np.vstack([chord_scores, np.full((1, beat_count), _NO_CHORD_SCORE)])
    silent = ~active | (norms < 1e-9)
    similarity[:NO_CHORD_STATE, silent] = -np.inf
    logits = _SOFTMAX_SHARPNESS * similarity
    logits -= logits.max(axis=0, keepdims=True)
    probabilities = np.exp(logits)
    probabilities /= probabilities.sum(axis=0, keepdims=True)

    transition = librosa.sequence.transition_loop(NO_CHORD_STATE + 1, _SELF_TRANSITION)
    states = librosa.sequence.viterbi_discriminative(probabilities, transition)
    confidence = probabilities[states, np.arange(beat_count)]
    return states, confidence


def chord_segments(
    states: np.ndarray,
    confidence: np.ndarray,
    grid: np.ndarray,
    duration_seconds: float,
) -> tuple[ChordSegment, ...]:
    """Merge runs of equal beat states into timed chord segments."""
    ends = np.append(grid[1:], max(duration_seconds, grid[-1] + 1e-3))
    segments: list[ChordSegment] = []
    run_start = 0
    for index in range(1, len(states) + 1):
        if index < len(states) and states[index] == states[run_start]:
            continue
        state = int(states[run_start])
        root, quality = (None, None)
        if state != NO_CHORD_STATE:
            pitch_class, quality = CHORD_LABELS[state]
            root = PITCH_CLASS_NAMES[pitch_class]
        segments.append(
            ChordSegment(
                start_seconds=float(grid[run_start]),
                end_seconds=float(ends[index - 1]),
                root_note=root,
                quality=quality,
                confidence=float(np.clip(np.mean(confidence[run_start:index]), 0.0, 1.0)),
            )
        )
        run_start = index
    return tuple(segments)


def estimate_key(
    profile: np.ndarray, chords: tuple[ChordSegment, ...]
) -> KeyEstimate:
    """Key from a 12-bin pitch-class profile and the chord timeline.

    The pitch collection is the key maximising its Krumhansl–Kessler
    correlation plus the share of chord time whose triad lies entirely inside
    its scale. The chord term matters with open guitar voicings, whose
    doubled strings (E, G, B) pull the raw profile toward E minor / G major.
    Between that key and its relative, which share every pitch class, the one
    whose tonic triad has more support in ``chords`` (share of chord time,
    opening the piece, closing it) wins.

    Confidence is the product of two parts. How diatonic the profile is to
    the chosen scale: the share of chroma energy inside it, rescaled so flat
    chroma gives 0 and a purely diatonic profile gives 1. And how clearly the
    tonic was chosen over the relative key: 0.5 for a tie up to 1.
    """
    profile = np.asarray(profile, dtype=float)
    if profile.shape != (12,) or not np.any(profile > 0):
        raise ValueError("The key profile must be 12 non-negative, non-zero bins.")
    correlations = {}
    for tonic in range(12):
        correlations[(tonic, "major")] = _correlation(profile, np.roll(_MAJOR_PROFILE, tonic))
        correlations[(tonic, "minor")] = _correlation(profile, np.roll(_MINOR_PROFILE, tonic))

    best = max(
        correlations,
        key=lambda key: correlations[key] + _diatonic_chord_share(key, chords),
    )
    relative = _relative_key(best)
    pair = {best, relative}

    decision = {
        key: correlations[key] + _TONIC_EVIDENCE_WEIGHT * _tonic_evidence(key, chords)
        for key in pair
    }
    chosen = max(pair, key=decision.get)
    other = relative if chosen == best else best

    in_scale = sum(
        profile[(best[0] + interval) % 12] for interval in SCALE_INTERVALS[best[1]]
    )
    share = float(in_scale / profile.sum())
    collection_confidence = float(
        np.clip((share - _CHANCE_IN_SCALE) / (1 - _CHANCE_IN_SCALE), 0.0, 1.0)
    )
    tonic_confidence = float(np.clip(0.5 + decision[chosen] - decision[other], 0.5, 1.0))
    return KeyEstimate(
        root_note=PITCH_CLASS_NAMES[chosen[0]],
        scale=chosen[1],
        confidence=round(collection_confidence * tonic_confidence, 4),
        alternative=f"{PITCH_CLASS_NAMES[other[0]]} {other[1]}",
    )


def _relative_key(key: tuple[int, str]) -> tuple[int, str]:
    tonic, mode = key
    if mode == "major":
        return (tonic + 9) % 12, "minor"
    return (tonic + 3) % 12, "major"


def _diatonic_chord_share(key: tuple[int, str], chords: tuple[ChordSegment, ...]) -> float:
    """Share of chord time whose whole triad belongs to ``key``'s scale."""
    tonic, mode = key
    scale = {(tonic + interval) % 12 for interval in SCALE_INTERVALS[mode]}
    sounding = [segment for segment in chords if segment.is_chord]
    total = sum(segment.end_seconds - segment.start_seconds for segment in sounding)
    if total <= 0:
        return 0.0
    inside = sum(
        segment.end_seconds - segment.start_seconds
        for segment in sounding
        if {
            (segment.root_pitch_class + interval) % 12
            for interval in CHORD_QUALITY_INTERVALS[segment.quality]
        }
        <= scale
    )
    return inside / total


def _tonic_evidence(key: tuple[int, str], chords: tuple[ChordSegment, ...]) -> float:
    """Share of chord time on the tonic triad, +1 if it opens, +0.5 if it closes."""
    tonic, mode = key
    sounding = [segment for segment in chords if segment.is_chord]
    if not sounding:
        return 0.0

    def is_tonic(segment: ChordSegment) -> bool:
        return segment.root_pitch_class == tonic and segment.quality == mode

    total = sum(segment.end_seconds - segment.start_seconds for segment in sounding)
    share = sum(
        segment.end_seconds - segment.start_seconds
        for segment in sounding
        if is_tonic(segment)
    ) / total
    return share + (1.0 if is_tonic(sounding[0]) else 0.0) + (
        0.5 if is_tonic(sounding[-1]) else 0.0
    )


def _correlation(first: np.ndarray, second: np.ndarray) -> float:
    """Pearson correlation; a flat profile (no pitch evidence) correlates 0."""
    if float(np.std(first)) < 1e-12:
        return 0.0
    return float(np.corrcoef(first, second)[0, 1])
