"""Audio analysis: the only layer that imports librosa and numpy.

A recording goes in, a :class:`midi_generator.domain.MusicAnalysis` comes out;
generation never touches audio. See ``docs/AUDIO_ANALYSIS.md``.
"""

from .analyzer import analyze_audio, analyze_signal
from .loader import DEFAULT_SAMPLE_RATE, AudioSignal, load_audio

__all__ = [
    "DEFAULT_SAMPLE_RATE",
    "AudioSignal",
    "analyze_audio",
    "analyze_signal",
    "load_audio",
]
