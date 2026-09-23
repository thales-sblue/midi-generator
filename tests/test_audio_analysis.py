"""Audio analysis: loading, beat grid, metre, chords, key and the full flow.

Signal-level estimates are checked with tolerances (tempo within 2 BPM, beats
within 30 ms), never for exact floats. Recordings are synthesised strummed
guitar (``audio_synthesis.py``); a real-recording check is a manual step
documented in ``docs/AUDIO_ANALYSIS.md``.
"""

import numpy as np
import pytest
from mido import MidiFile

from audio_synthesis import SAMPLE_RATE, strummed_progression, write_wav
from midi_generator.audio import analyze_audio, load_audio
from midi_generator.audio.harmony import (
    CHORD_LABELS,
    NO_CHORD_STATE,
    chord_segments,
    chord_templates,
    decode_chords,
    estimate_key,
)
from midi_generator.audio.rhythm import (
    estimate_meter,
    extend_backward,
    harmonic_change,
    merge_strums,
    regularize_beats,
    snap_to_onsets,
    tempo_confidence,
)
from midi_generator.domain import ChordSegment, TimeSignature, scale_pitch_classes
from midi_generator.exporters import MidiExporter
from midi_generator.generation import generate_accompaniment
from midi_generator.generation.drums import KICK_PITCH, SNARE_PITCH

BEAT_TOLERANCE = 0.03  # seconds
TEMPO_TOLERANCE = 2.0  # BPM

AXIS = ("Am", "F", "C", "G")


@pytest.fixture(scope="module")
def recordings(tmp_path_factory):
    """Synthesise each test recording once and analyse it once."""
    folder = tmp_path_factory.mktemp("audio")
    specs = {
        "axis_92": dict(progression=AXIS * 2, bpm=92),
        "pop_120_eighths": dict(
            progression=("C", "G", "Am", "F") * 2, bpm=120, strums_per_beat=2
        ),
        "waltz_110": dict(
            progression=("D", "G", "A", "D", "G", "A", "D", "D"), bpm=110, beats_per_bar=3
        ),
        "pickup_100": dict(progression=("Em", "C", "G", "D") * 2, bpm=100, pickup=("D",)),
        "sevenths_100": dict(progression=("Am7", "Fmaj7", "C", "G7") * 2, bpm=100),
        "slow_64": dict(progression=("Em", "C", "G", "D") * 2, bpm=64),
        # Eighth-note strums at 60 BPM read as 120 BPM without a hint; a rough
        # hint only has to pick the tempo octave.
        "slow_eighths_60": dict(
            progression=("Em", "C", "G", "D") * 2, bpm=60, strums_per_beat=2
        ),
    }
    hints = {"slow_eighths_60": 66}
    results = {}
    for name, spec in specs.items():
        path = write_wav(folder / f"{name}.wav", strummed_progression(**spec))
        results[name] = (spec, path, analyze_audio(path, tempo_hint=hints.get(name)))
    return results


# --- Loading -----------------------------------------------------------------


def test_load_audio_returns_mono_samples_at_the_analysis_rate(tmp_path):
    stereo = np.stack([np.sin(np.linspace(0, 400, 44100)), np.zeros(44100)], axis=1)
    path = write_wav(tmp_path / "stereo.wav", stereo * 0.5, sample_rate=44100)

    signal = load_audio(path)

    assert signal.samples.ndim == 1
    assert signal.sample_rate == SAMPLE_RATE
    assert signal.duration_seconds == pytest.approx(1.0, abs=0.01)
    assert signal.source == "stereo.wav"


def test_load_audio_rejects_missing_silent_and_undecodable_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_audio(tmp_path / "missing.wav")
    silent = write_wav(tmp_path / "silent.wav", np.zeros(SAMPLE_RATE))
    with pytest.raises(ValueError, match="silent"):
        load_audio(silent)
    garbage = tmp_path / "garbage.wav"
    garbage.write_bytes(b"not audio at all")
    with pytest.raises(ValueError, match="decode"):
        load_audio(garbage)


# --- Beat grid ---------------------------------------------------------------


def test_regularize_beats_fills_skipped_beats_and_extends_to_the_end():
    detected = np.array([0.5, 1.0, 1.5, 2.5, 3.0])  # the beat at 2.0 was missed
    grid = regularize_beats(detected, duration_seconds=4.2)
    assert grid == pytest.approx([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])


def test_snap_to_onsets_removes_the_tracker_lag_and_lands_on_attacks():
    attacks = np.array([0.50, 1.00, 1.52, 2.00, 2.50])
    tracked = np.array([0.55, 1.05, 1.55, 2.05, 2.55, 3.05])  # 50 ms late
    snapped = snap_to_onsets(tracked, attacks)
    # Matched beats land on their attacks; the last one, with no attack,
    # still loses the 50 ms lag.
    assert snapped == pytest.approx([0.50, 1.00, 1.52, 2.00, 2.50, 3.00])


def test_snap_to_onsets_spaces_a_beat_without_attack_between_its_neighbours():
    attacks = np.array([0.50, 1.00, 2.00, 2.50])  # the strum at 1.5 was missed
    tracked = np.array([0.50, 1.00, 1.47, 2.00, 2.50])
    assert snap_to_onsets(tracked, attacks) == pytest.approx([0.5, 1.0, 1.5, 2.0, 2.5])


def test_merge_strums_keeps_the_first_onset_of_each_strum():
    onsets = np.array([0.50, 0.53, 1.00, 1.04, 1.20])
    assert merge_strums(onsets) == pytest.approx([0.50, 1.00, 1.20])


def test_snap_to_onsets_leaves_beats_without_nearby_attacks_alone():
    tracked = np.array([0.5, 1.0, 1.5])
    assert snap_to_onsets(tracked, np.array([5.0])) == pytest.approx(tracked)
    assert snap_to_onsets(tracked, np.array([])) == pytest.approx(tracked)
    # Attacks 60 ms early and 60 ms late: the median lag is 0 and, after the
    # correction, no beat sits within 35 ms of an attack.
    uneven = np.array([0.44, 1.06])
    assert snap_to_onsets(np.array([0.5, 1.0]), uneven) == pytest.approx([0.5, 1.0])


def test_extend_backward_recovers_trimmed_leading_beats_but_not_silence():
    attacks = np.array([0.30, 1.24, 2.18, 3.12, 4.06])
    tracked = np.array([2.18, 3.12, 4.06])
    assert extend_backward(tracked, attacks) == pytest.approx(attacks)
    # With no attack where the earlier beat would be, nothing is invented.
    assert extend_backward(tracked, attacks[2:]) == pytest.approx(tracked)


def test_regularize_beats_needs_two_beats():
    with pytest.raises(ValueError):
        regularize_beats(np.array([0.5]), 3.0)


def test_tempo_confidence_rewards_a_steady_pulse():
    steady = np.arange(0, 10, 0.5)
    shaky = steady + np.tile([0.0, 0.08], 10)
    assert tempo_confidence(steady) == pytest.approx(1.0)
    assert tempo_confidence(shaky) < 0.5


def test_estimate_meter_finds_phase_from_harmonic_change_and_accents():
    beats = 24
    change = np.zeros(beats)
    change[[1, 5, 9, 13, 17, 21]] = 1.0  # chords change on beats 1, 5, 9...
    accents = np.full(beats, 0.5)
    accents[1::4] = 1.0
    meter = estimate_meter(change, accents)
    assert (meter.beats_per_bar, meter.first_downbeat_index) == (4, 1)
    assert meter.confidence > 0.3


def test_estimate_meter_tells_three_from_four():
    change = np.zeros(24)
    change[::3] = 1.0
    change[0] = 0.0  # beat 0 has no predecessor
    meter = estimate_meter(change, np.ones(24))
    assert (meter.beats_per_bar, meter.first_downbeat_index) == (3, 0)


def test_estimate_meter_rejects_too_few_beats():
    with pytest.raises(ValueError):
        estimate_meter(np.zeros(5), np.zeros(5))


def test_harmonic_change_is_zero_for_a_held_chord():
    chroma = np.tile(np.array([[1.0], [0.0], [0.5]] + [[0.0]] * 9), (1, 4))
    chroma[:, 3] = np.roll(chroma[:, 3], 5)
    change = harmonic_change(chroma)
    assert change[:3] == pytest.approx([0.0, 0.0, 0.0])
    assert change[3] > 0.9


# --- Chords and key ------------------------------------------------------------


def _triad_chroma(root, quality):
    vector = np.zeros(12)
    for interval in (0, 4, 7) if quality == "major" else (0, 3, 7):
        vector[(root + interval) % 12] = 1.0
    return vector


def test_chord_templates_cover_all_major_and_minor_triads():
    templates = chord_templates()
    assert templates.shape == (24, 12)
    assert np.linalg.norm(templates, axis=1) == pytest.approx(np.ones(24))
    assert len(CHORD_LABELS) == 24


def test_decode_chords_labels_beats_and_marks_silence():
    columns = [_triad_chroma(9, "minor")] * 3 + [_triad_chroma(5, "major")] * 3
    columns += [np.zeros(12)]
    chroma = np.stack(columns, axis=1)
    active = np.array([True] * 6 + [False])

    states, confidence = decode_chords(chroma, active)

    assert [CHORD_LABELS[s] if s != NO_CHORD_STATE else None for s in states] == (
        [(9, "minor")] * 3 + [(5, "major")] * 3 + [None]
    )
    assert np.all((confidence > 0.5) & (confidence <= 1.0))


def test_decode_chords_smooths_a_single_ambiguous_beat():
    noisy = _triad_chroma(9, "minor") * 0.6 + _triad_chroma(0, "major") * 0.5
    chroma = np.stack([_triad_chroma(9, "minor")] * 3 + [noisy] + [_triad_chroma(9, "minor")] * 3, axis=1)
    states, _ = decode_chords(chroma, np.ones(7, dtype=bool))
    assert set(states.tolist()) == {CHORD_LABELS.index((9, "minor"))}


def test_decode_chords_uses_the_bass_to_break_a_seventh_chord_tie():
    fmaj7 = _triad_chroma(5, "major") + _triad_chroma(9, "minor")  # F A C E
    chroma = np.stack([fmaj7] * 4, axis=1)
    bass = np.zeros((12, 4))
    bass[5] = 1.0  # F in the bass register
    bass[0] = 0.6  # and its fifth
    states, _ = decode_chords(chroma, np.ones(4, dtype=bool), bass)
    assert set(states.tolist()) == {CHORD_LABELS.index((5, "major"))}


def test_chord_segments_merge_runs_into_timed_chords():
    states = np.array([21, 21, 5, 5, NO_CHORD_STATE])  # Am Am F F N
    confidence = np.array([0.9, 0.7, 0.8, 0.8, 1.0])
    grid = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
    segments = chord_segments(states, confidence, grid, duration_seconds=3.2)
    assert [(s.start_seconds, s.end_seconds, s.symbol) for s in segments] == [
        (0.5, 1.5, "Am"),
        (1.5, 2.5, "F"),
        (2.5, 3.2, "N"),
    ]
    assert segments[0].confidence == pytest.approx(0.8)


def test_estimate_key_uses_chords_to_choose_between_relative_keys():
    profile = sum(_triad_chroma(root, quality) for root, quality in
                  ((9, "minor"), (5, "major"), (0, "major"), (7, "major")))

    def timeline(*symbols):
        return tuple(
            ChordSegment(i, i + 1, root, quality, 0.9)
            for i, (root, quality) in enumerate(symbols)
        )

    starts_on_am = estimate_key(
        profile, timeline(("A", "minor"), ("F", "major"), ("C", "major"), ("G", "major"))
    )
    starts_on_c = estimate_key(
        profile, timeline(("C", "major"), ("G", "major"), ("A", "minor"), ("F", "major"))
    )
    assert starts_on_am.name == "A minor"
    assert starts_on_am.alternative == "C major"
    assert starts_on_c.name == "C major"
    assert 0 < starts_on_am.confidence <= 1


def test_estimate_key_lets_diatonic_chords_outvote_a_skewed_profile():
    # Open voicings double E, G and B, pulling the raw profile toward E minor
    # even though every chord (Am F C G) belongs to A minor / C major.
    profile = sum(_triad_chroma(root, quality) for root, quality in
                  ((9, "minor"), (5, "major"), (0, "major"), (7, "major")))
    profile = profile + 3.0 * np.eye(12)[4] + 2.0 * np.eye(12)[7] + 2.0 * np.eye(12)[11]
    chords = tuple(
        ChordSegment(i, i + 1, root, quality, 0.9)
        for i, (root, quality) in enumerate(
            [("A", "minor"), ("F", "major"), ("C", "major"), ("G", "major")]
        )
    )
    assert estimate_key(profile, ()).name in {"E minor", "G major"}
    assert estimate_key(profile, chords).name == "A minor"


def test_estimate_key_has_no_confidence_without_pitch_evidence():
    key = estimate_key(np.ones(12), ())
    assert key.confidence == 0.0
    with pytest.raises(ValueError):
        estimate_key(np.zeros(12), ())


# --- Recordings ----------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "axis_92",
        "pop_120_eighths",
        "waltz_110",
        "pickup_100",
        "sevenths_100",
        "slow_64",
        "slow_eighths_60",
    ],
)
def test_tempo_is_within_tolerance(recordings, name):
    spec, _, analysis = recordings[name]
    assert analysis.tempo_bpm == pytest.approx(spec["bpm"], abs=TEMPO_TOLERANCE)
    assert analysis.tempo_confidence > 0.5


@pytest.mark.parametrize(
    "name",
    [
        "axis_92",
        "pop_120_eighths",
        "waltz_110",
        "pickup_100",
        "sevenths_100",
        "slow_64",
        "slow_eighths_60",
    ],
)
def test_beats_land_on_the_strums(recordings, name):
    spec, _, analysis = recordings[name]
    period = 60.0 / spec["bpm"]
    first_downbeat = 0.5 + len(spec.get("pickup", ())) * period
    per_bar = spec.get("beats_per_bar", 4)
    expected = [
        first_downbeat + index * period
        for index in range(len(spec["progression"]) * per_bar)
    ]
    grid = analysis.grid
    assert grid.first_downbeat_seconds == pytest.approx(first_downbeat, abs=BEAT_TOLERANCE)
    downbeat = grid.first_downbeat_index
    assert grid.beat_times[downbeat : downbeat + len(expected)] == pytest.approx(
        expected, abs=BEAT_TOLERANCE
    )


@pytest.mark.parametrize(
    ("name", "metre"),
    [("axis_92", TimeSignature(4, 4)), ("waltz_110", TimeSignature(3, 4)),
     ("pickup_100", TimeSignature(4, 4))],
)
def test_metre_and_first_downbeat(recordings, name, metre):
    spec, _, analysis = recordings[name]
    assert analysis.time_signature == metre
    assert analysis.grid.first_downbeat_index == len(spec.get("pickup", ()))


@pytest.mark.parametrize(
    "name",
    [
        "axis_92",
        "pop_120_eighths",
        "waltz_110",
        "pickup_100",
        "sevenths_100",
        "slow_64",
        "slow_eighths_60",
    ],
)
def test_progression_is_recovered_bar_by_bar(recordings, name):
    spec, _, analysis = recordings[name]
    # Seventh chords are reported by their triad.
    expected = [chord.replace("maj7", "").replace("7", "") for chord in spec["progression"]]
    recovered = list(analysis.progression()[: len(expected)])
    matches = sum(a == b for a, b in zip(recovered, expected))
    assert analysis.bar_count >= len(expected)
    assert matches >= len(expected) - 1, recovered


def test_seventh_chords_are_read_by_their_triad_and_bass_root(recordings):
    _, _, analysis = recordings["sevenths_100"]
    assert analysis.progression()[:8] == AXIS * 2


def test_chord_timeline_has_times_and_confidence(recordings):
    _, _, analysis = recordings["axis_92"]
    chords = [segment for segment in analysis.chords if segment.is_chord]
    assert [segment.symbol for segment in chords[:4]] == list(AXIS)
    bar = 4 * 60.0 / 92
    assert chords[1].start_seconds == pytest.approx(0.5 + bar, abs=BEAT_TOLERANCE)
    assert chords[1].end_seconds == pytest.approx(0.5 + 2 * bar, abs=BEAT_TOLERANCE)
    assert all(0.5 < segment.confidence <= 1 for segment in chords)


@pytest.mark.parametrize(
    ("name", "key"),
    [("axis_92", "A minor"), ("pop_120_eighths", "C major"),
     ("waltz_110", "D major"), ("pickup_100", "E minor"),
     ("sevenths_100", "A minor"), ("slow_64", "E minor")],
)
def test_key_is_estimated_with_confidence(recordings, name, key):
    _, _, analysis = recordings[name]
    assert analysis.key.name == key
    assert 0.3 < analysis.key.confidence <= 1


def test_summary_reads_like_a_lead_sheet(recordings):
    _, _, analysis = recordings["axis_92"]
    summary = analysis.summary()
    assert "Key: A minor" in summary
    assert "Time signature: 4/4" in summary
    for number, chord in enumerate(AXIS * 2, start=1):
        assert f"Bar {number}: {chord}" in summary


def test_beats_per_bar_override_is_honoured(recordings):
    _, path, _ = recordings["waltz_110"]
    forced = analyze_audio(path, beats_per_bar=4)
    assert forced.time_signature == TimeSignature(4, 4)


@pytest.mark.parametrize("kwargs", [{"beats_per_bar": 1}, {"beats_per_bar": True},
                                    {"tempo_hint": 5}])
def test_analyze_audio_rejects_bad_options(recordings, kwargs):
    _, path, _ = recordings["axis_92"]
    with pytest.raises(ValueError):
        analyze_audio(path, **kwargs)


def test_too_short_a_recording_is_rejected(tmp_path):
    path = write_wav(
        tmp_path / "short.wav", strummed_progression(("Am",), bpm=120, tail=0.1)
    )
    with pytest.raises(ValueError):
        analyze_audio(path)


# --- Full flow: audio -> analysis -> bass + drums -> aligned MIDI -------------


def test_accompaniment_from_audio_follows_and_aligns_with_the_recording(recordings, tmp_path):
    spec, _, analysis = recordings["pickup_100"]
    accompaniment = generate_accompaniment(analysis)

    # Bass: root of every detected bar's chord, inside the detected key.
    bass_roots = [note.pitch % 12 for note in accompaniment.bass.notes]
    expected_roots = [{"Em": 4, "C": 0, "G": 7, "D": 2}[c] for c in spec["progression"]]
    assert bass_roots[: len(expected_roots)] == expected_roots
    key_classes = scale_pitch_classes(analysis.key.root_note, analysis.key.scale)
    assert set(bass_roots) <= key_classes

    # Drums and bass land on the recording's beats once exported with the map.
    exporter = MidiExporter()
    drums = exporter.export(
        accompaniment.drums, tmp_path / "drums.mid", tempo_map=accompaniment.tempo_map
    )
    bass = exporter.export(
        accompaniment.bass, tmp_path / "bass.mid", tempo_map=accompaniment.tempo_map
    )
    period = 60.0 / spec["bpm"]
    downbeat = 0.5 + period  # one pickup beat
    beat_times = [downbeat + index * period for index in range(32)]

    def onsets(path, pitch=None):
        elapsed, found = 0.0, []
        for message in MidiFile(path):
            elapsed += message.time
            if message.type == "note_on" and (pitch is None or message.note == pitch):
                found.append(elapsed)
        return found

    assert onsets(drums, KICK_PITCH)[:16] == pytest.approx(beat_times[0::2], abs=BEAT_TOLERANCE)
    assert onsets(drums, SNARE_PITCH)[:16] == pytest.approx(beat_times[1::2], abs=BEAT_TOLERANCE)
    assert onsets(bass)[:8] == pytest.approx(beat_times[0::4], abs=BEAT_TOLERANCE)
