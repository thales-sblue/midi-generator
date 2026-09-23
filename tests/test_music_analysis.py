import json

import pytest

from midi_generator.domain import (
    BeatGrid,
    ChordSegment,
    KeyEstimate,
    Measure,
    MusicAnalysis,
    TempoChange,
    TimeSignature,
    build_measures,
    tempo_map_for_grid,
)


def _steady_grid(*, beats=17, period=0.5, start=0.25, downbeat=0, per_bar=4):
    return BeatGrid(
        beat_times=tuple(start + index * period for index in range(beats)),
        first_downbeat_index=downbeat,
        beats_per_bar=per_bar,
    )


def _segment(start, end, root, quality, confidence=0.9):
    return ChordSegment(start, end, root, quality, confidence)


def _analysis(grid, chords, *, energies=None):
    energies = energies or [1.0] * grid.bar_count
    return MusicAnalysis(
        source="test.wav",
        duration_seconds=grid.beat_times[-1] + 0.5,
        grid=grid,
        detected_beats=grid.beat_times,
        tempo_confidence=0.9,
        meter_confidence=0.7,
        key=KeyEstimate("A", "minor", 0.8, alternative="C major"),
        chords=tuple(chords),
        measures=build_measures(grid, chords, energies),
    )


# --- BeatGrid: seconds <-> beats <-> bars -----------------------------------


def test_grid_tempo_and_bar_count():
    grid = _steady_grid()
    assert grid.tempo_bpm == pytest.approx(120.0)
    assert grid.bar_count == 4  # 16 beat intervals after the downbeat
    assert grid.first_downbeat_seconds == 0.25


def test_seconds_to_beat_counts_from_the_first_downbeat():
    grid = _steady_grid(downbeat=1)  # beat at 0.25 s is a one-beat pickup
    assert grid.seconds_to_beat(0.75) == pytest.approx(0.0)
    assert grid.seconds_to_beat(1.0) == pytest.approx(0.5)
    assert grid.seconds_to_beat(0.25) == pytest.approx(-1.0)
    # Extrapolates past both ends with the edge intervals.
    assert grid.seconds_to_beat(0.0) == pytest.approx(-1.5)
    assert grid.seconds_to_beat(grid.beat_times[-1] + 0.25) == pytest.approx(15.5)


def test_seconds_to_beat_follows_tempo_drift_beat_by_beat():
    # The performance slows down: intervals of 0.5 s, then 0.6 s.
    grid = BeatGrid((0.0, 0.5, 1.0, 1.6, 2.2), 0, 4)
    assert grid.seconds_to_beat(1.3) == pytest.approx(2.5)
    assert grid.beat_to_seconds(2.5) == pytest.approx(1.3)
    # A global BPM would have put 1.3 s at beat 2.6 (1.3 / 0.5).


def test_beat_to_seconds_inverts_seconds_to_beat():
    grid = BeatGrid((0.1, 0.62, 1.1, 1.65, 2.2, 2.71), 1, 2)
    for seconds in (0.0, 0.3, 0.62, 1.4, 2.5, 3.0):
        assert grid.beat_to_seconds(grid.seconds_to_beat(seconds)) == pytest.approx(seconds)


def test_beat_to_bar():
    grid = _steady_grid(per_bar=4)
    assert grid.beat_to_bar(0.0) == (1, 0.0)
    assert grid.beat_to_bar(3.5) == (1, 3.5)
    assert grid.beat_to_bar(4.0) == (2, 0.0)
    assert grid.beat_to_bar(9.25) == (3, 1.25)
    assert grid.beat_to_bar(-1.0) == (0, 3.0)  # pickup beat
    three = _steady_grid(per_bar=3)
    assert three.beat_to_bar(7.0) == (3, 1.0)


def test_bar_bounds_and_incomplete_last_bar():
    grid = _steady_grid(beats=12)  # 11 intervals -> 2 complete bars of 4
    assert grid.bar_count == 2
    assert grid.bar_bounds_seconds(2) == pytest.approx((2.25, 4.25))
    with pytest.raises(ValueError):
        grid.bar_bounds_seconds(3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"beat_times": (0.5,), "first_downbeat_index": 0, "beats_per_bar": 4},
        {"beat_times": (0.5, 0.4), "first_downbeat_index": 0, "beats_per_bar": 4},
        {"beat_times": (0.0, 0.5), "first_downbeat_index": 2, "beats_per_bar": 4},
        {"beat_times": (0.0, 0.5), "first_downbeat_index": 0, "beats_per_bar": 0},
        {"beat_times": [0.0, 0.5], "first_downbeat_index": 0, "beats_per_bar": 4},
    ],
)
def test_grid_rejects_invalid_input(kwargs):
    with pytest.raises(ValueError):
        BeatGrid(**kwargs)


# --- Chords, key, measures ---------------------------------------------------


def test_chord_segment_symbols():
    assert _segment(0, 1, "A", "minor").symbol == "Am"
    assert _segment(0, 1, "F", "major").symbol == "F"
    assert _segment(0, 1, "C#", "minor").root_pitch_class == 1
    no_chord = _segment(0, 1, None, None)
    assert no_chord.symbol == "N"
    assert not no_chord.is_chord
    assert no_chord.root_pitch_class is None


@pytest.mark.parametrize(
    "args",
    [
        (1.0, 1.0, "A", "minor", 0.5),
        (0.0, 1.0, "A", None, 0.5),
        (0.0, 1.0, "H", "minor", 0.5),
        (0.0, 1.0, "A", "diminished", 0.5),
        (0.0, 1.0, "A", "minor", 1.5),
    ],
)
def test_chord_segment_rejects_invalid_input(args):
    with pytest.raises(ValueError):
        ChordSegment(*args)


def test_key_estimate_validates_against_the_scale_table():
    assert KeyEstimate("A", "minor", 0.8).name == "A minor"
    with pytest.raises(ValueError):
        KeyEstimate("A", "ionian", 0.8)
    with pytest.raises(ValueError):
        KeyEstimate("A", "minor", -0.1)


def test_build_measures_maps_a_progression_to_bars():
    grid = _steady_grid()  # bars of 2 s starting at 0.25 s
    chords = [
        _segment(0.25, 2.25, "A", "minor"),
        _segment(2.25, 4.25, "F", "major"),
        _segment(4.25, 6.25, "C", "major"),
        _segment(6.25, 8.25, "G", "major"),
    ]
    measures = build_measures(grid, chords, [0.2, 0.4, 0.6, 1.0])
    assert [m.chord for m in measures] == ["Am", "F", "C", "G"]
    assert [m.number for m in measures] == [1, 2, 3, 4]
    assert measures[1].start_seconds == pytest.approx(2.25)
    assert measures[1].end_seconds == pytest.approx(4.25)
    assert measures[3].energy == 1.0


def test_build_measures_lists_a_mid_bar_change_and_picks_the_longest():
    grid = _steady_grid(beats=5)  # one bar, 0.25 .. 2.25, beat = 0.5 s
    chords = [
        _segment(0.0, 0.85, "A", "minor"),  # 0.6 s inside the bar
        _segment(0.85, 1.35, "E", "major"),  # 0.5 s
        _segment(1.35, 2.25, "F", "major"),  # 0.9 s
        _segment(2.25, 3.0, "G", "major"),  # outside
    ]
    (measure,) = build_measures(grid, chords, [0.5])
    assert measure.chord == "F"
    assert measure.chords == ("Am", "E", "F")


def test_build_measures_ignores_tiny_overlaps_and_handles_silence():
    grid = _steady_grid(beats=9)
    chords = [
        _segment(0.25, 2.35, "A", "minor"),  # spills 0.1 s into bar 2
        _segment(2.35, 4.25, None, None),
    ]
    first, second = build_measures(grid, chords, [1.0, 0.0])
    assert first.chords == ("Am",)
    assert second.chord == "N"
    assert second.chords == ("N",)


def test_build_measures_without_chords_is_no_chord():
    grid = _steady_grid(beats=5)
    (measure,) = build_measures(grid, [], [0.0])
    assert measure.chord == "N"


def test_build_measures_requires_one_energy_per_bar():
    with pytest.raises(ValueError):
        build_measures(_steady_grid(), [], [1.0])


def test_measure_rejects_invalid_energy():
    with pytest.raises(ValueError):
        Measure(1, 0.0, 1.0, "Am", ("Am",), 1.2)


# --- MusicAnalysis -----------------------------------------------------------


def test_music_analysis_exposes_timeline_and_progression():
    grid = _steady_grid()
    chords = [
        _segment(0.25, 2.25, "A", "minor"),
        _segment(2.25, 4.25, "F", "major"),
        _segment(4.25, 6.25, "C", "major"),
        _segment(6.25, 8.25, "G", "major"),
    ]
    analysis = _analysis(grid, chords)
    assert analysis.tempo_bpm == pytest.approx(120.0)
    assert analysis.time_signature == TimeSignature(4, 4)
    assert analysis.bar_count == 4
    assert analysis.progression() == ("Am", "F", "C", "G")

    summary = analysis.summary()
    assert "Tempo: 120.0 BPM" in summary
    assert "Key: A minor" in summary
    assert "Bar 1: Am" in summary
    assert "Bar 4: G" in summary


def test_music_analysis_dict_is_json_safe_and_versioned():
    grid = _steady_grid(beats=9)
    analysis = _analysis(
        grid,
        [_segment(0.25, 2.25, "A", "minor"), _segment(2.25, 4.25, "F", "major")],
        energies=[0.5, 1.0],
    )
    data = json.loads(json.dumps(analysis.to_dict()))
    assert data["schema"] == "music_analysis"
    assert data["schema_version"] == 1
    assert data["tempo"] == 120.0
    assert data["time_signature"] == "4/4"
    assert data["key"] == {
        "key": "A",
        "mode": "minor",
        "confidence": 0.8,
        "alternative": "C major",
    }
    assert data["downbeats"] == [0.25, 2.25]
    assert data["chords"][1] == {"start": 2.25, "end": 4.25, "chord": "F", "confidence": 0.9}
    assert [m["chord"] for m in data["measures"]] == ["Am", "F"]


def test_music_analysis_requires_one_measure_per_bar():
    grid = _steady_grid()
    with pytest.raises(ValueError):
        MusicAnalysis(
            source="x.wav",
            duration_seconds=9.0,
            grid=grid,
            detected_beats=grid.beat_times,
            tempo_confidence=0.9,
            meter_confidence=0.9,
            key=KeyEstimate("C", "major", 0.5),
            chords=(),
            measures=(),
        )


# --- Tempo map ---------------------------------------------------------------


def test_tempo_map_for_a_steady_grid_with_lead_in():
    grid = _steady_grid(start=1.0)  # first downbeat at 1.0 s, 120 BPM
    tempo_map = tempo_map_for_grid(grid, bars=2, ticks_per_beat=480)
    # One bar of lead-in stretched over 1.0 s -> 0.25 s per beat.
    assert tempo_map.lead_in_ticks == 4 * 480
    assert tempo_map.changes == (
        TempoChange(0, 250_000),
        TempoChange(4 * 480, 500_000),
    )


def test_tempo_map_follows_every_beat_and_skips_repeats():
    grid = BeatGrid((0.0, 0.5, 1.0, 1.6, 2.2), 0, 4)
    tempo_map = tempo_map_for_grid(grid, bars=1, ticks_per_beat=480)
    assert tempo_map.lead_in_ticks == 0
    assert tempo_map.changes == (
        TempoChange(0, 500_000),
        TempoChange(960, 600_000),
    )


def test_tempo_map_rejects_bars_outside_the_grid():
    with pytest.raises(ValueError):
        tempo_map_for_grid(_steady_grid(), bars=5, ticks_per_beat=480)
    with pytest.raises(ValueError):
        tempo_map_for_grid(_steady_grid(), bars=0, ticks_per_beat=480)
