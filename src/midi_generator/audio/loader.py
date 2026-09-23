"""Load a recording as a mono signal at a fixed analysis sample rate."""

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

DEFAULT_SAMPLE_RATE = 22050
# Peak amplitude under which a file is treated as silence.
_SILENCE_PEAK = 1e-4


@dataclass(frozen=True, eq=False)
class AudioSignal:
    """Mono samples in ``-1..1`` with the rate they were resampled to."""

    samples: np.ndarray
    sample_rate: int
    source: str

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / self.sample_rate


def load_audio(path: str | Path, *, sample_rate: int = DEFAULT_SAMPLE_RATE) -> AudioSignal:
    """Read any format libsndfile (or audioread) understands, mixed to mono.

    Raises ``FileNotFoundError`` for a missing file and ``ValueError`` for an
    unreadable, empty or silent one.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    try:
        samples, rate = librosa.load(path, sr=sample_rate, mono=True)
    except Exception as error:  # decoder errors vary by backend and format
        raise ValueError(f"Could not decode audio file {path.name}: {error}") from error
    if samples.size == 0:
        raise ValueError(f"Audio file {path.name} holds no samples.")
    if not np.all(np.isfinite(samples)):
        raise ValueError(f"Audio file {path.name} holds non-finite samples.")
    if float(np.max(np.abs(samples))) < _SILENCE_PEAK:
        raise ValueError(f"Audio file {path.name} is silent.")
    return AudioSignal(samples=samples, sample_rate=int(rate), source=path.name)
