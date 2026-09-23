"""Synthetic strummed-guitar recordings for audio-analysis tests.

Each string is a decaying additive tone (a few harmonics, brighter on the
attack), strummed low to high with a few milliseconds between strings, with
downstrokes on the first beat of each bar accented. It is crude next to a real
guitar but has what the analyzer listens for: onsets on the beats, triad pitch
content and bar accents. Fully deterministic.
"""

from pathlib import Path

import numpy as np
import soundfile

SAMPLE_RATE = 22050

# Open-position guitar voicings (MIDI pitches, low string first).
VOICINGS = {
    "Am": (45, 52, 57, 60, 64),
    "A": (45, 52, 57, 61, 64),
    "C": (48, 52, 55, 60, 64),
    "D": (50, 57, 62, 66),
    "Dm": (50, 57, 62, 65),
    "E": (40, 47, 52, 56, 59, 64),
    "Em": (40, 47, 52, 55, 59, 64),
    "F": (41, 48, 53, 57, 60, 65),
    "G": (43, 47, 50, 55, 59, 67),
    "Am7": (45, 52, 55, 60, 64),
    "Fmaj7": (41, 48, 52, 57, 64),
    "G7": (43, 47, 50, 53, 59, 67),
}


def _string(pitch, seconds, amplitude):
    samples = int(seconds * SAMPLE_RATE)
    time = np.arange(samples) / SAMPLE_RATE
    frequency = 440.0 * 2 ** ((pitch - 69) / 12)
    tone = np.zeros(samples)
    for harmonic in range(1, 7):
        if frequency * harmonic >= SAMPLE_RATE / 2:
            break
        decay = np.exp(-time * (2.5 + 1.8 * harmonic))
        tone += decay * np.sin(2 * np.pi * frequency * harmonic * time) / harmonic
    attack = np.minimum(1.0, time / 0.003)
    return amplitude * attack * tone


def strummed_progression(
    progression,
    *,
    bpm,
    beats_per_bar=4,
    lead_in=0.5,
    tail=1.0,
    strums_per_beat=1,
    pickup=(),
):
    """Mono float samples of ``progression``, one chord per bar.

    ``pickup`` lists chords strummed one per beat, unaccented, just before bar
    1; ``lead_in`` is the time of the first strum, pickup included.
    """
    beat = 60.0 / bpm
    first_downbeat = lead_in + len(pickup) * beat
    total = first_downbeat + len(progression) * beats_per_bar * beat + tail
    samples = np.zeros(int(total * SAMPLE_RATE) + SAMPLE_RATE)
    step = beat / strums_per_beat
    hits = [
        (lead_in + index * beat, chord, 0.6) for index, chord in enumerate(pickup)
    ]
    for bar, chord in enumerate(progression):
        for hit in range(beats_per_bar * strums_per_beat):
            onset = first_downbeat + (bar * beats_per_bar) * beat + hit * step
            accent = 1.0 if hit == 0 else (0.7 if hit % strums_per_beat == 0 else 0.45)
            hits.append((onset, chord, accent))
    for onset, chord, accent in hits:
        for order, pitch in enumerate(VOICINGS[chord]):
            start = int((onset + order * 0.008) * SAMPLE_RATE)
            tone = _string(pitch, step * 1.6, accent)
            end = min(len(samples), start + len(tone))
            samples[start:end] += tone[: end - start]
    return 0.8 * samples / np.max(np.abs(samples))


def write_wav(path: Path, samples, sample_rate=SAMPLE_RATE) -> Path:
    soundfile.write(path, samples, sample_rate)
    return path

