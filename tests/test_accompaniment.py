"""Bass and drums generated from a MusicAnalysis through the existing generators."""

import pytest
from mido import MidiFile

from midi_generator.domain import (
    BeatGrid,
    ChordSegment,
    KeyEstimate,
    MusicAnalysis,
    TimeSignature,
    build_measures,
)
from midi_generator.exporters import MidiExporter
from midi_generator.generation import (
    DRUM_STYLES,
    analysis_request,
    generate_accompaniment,
    generate_bass_from_analysis,
    generate_drums_from_analysis,
    harmonic_reference_clip,
)
from midi_generator.generation.drums import HIHAT_PITCH, KICK_PITCH, SNARE_PITCH
from midi_generator.integration import composition_to_payload, validate_payload_v1

PERIOD = 60 / 92  # 92 BPM


def make_analysis(
    progression=("Am", "F", "C", "G"),
    *,
    per_bar=4,
    first_downbeat=0.4,
    key=("A", "minor"),
    periods=None,
):
    beats = len(progression) * per_bar + 1
    times = [first_downbeat]
    for index in range(beats - 1):
        times.append(times[-1] + (periods[index] if periods else PERIOD))
    grid = BeatGrid(tuple(times), 0, per_bar)
    chords = []
    for bar, symbol in enumerate(progression):
        start, end = grid.bar_bounds_seconds(bar + 1)
        if symbol == "N":
            chords.append(ChordSegment(start, end, None, None, 0.9))
        else:
            quality = "minor" if symbol.endswith("m") else "major"
            chords.append(ChordSegment(start, end, symbol.rstrip("m"), quality, 0.9))
    return MusicAnalysis(
        source="guitar.wav",
        duration_seconds=times[-1] + 1.0,
        grid=grid,
        detected_beats=grid.beat_times,
        tempo_confidence=0.9,
        meter_confidence=0.8,
        key=KeyEstimate(*key, 0.8),
        chords=tuple(chords),
        measures=build_measures(grid, chords, [0.5] * len(progression)),
    )


def test_analysis_request_carries_tempo_key_metre_and_length():
    request = analysis_request(make_analysis(per_bar=3), seed=11)
    assert request.bpm == 92
    assert (request.root_note, request.scale) == ("A", "minor")
    assert request.time_signature == TimeSignature(3, 4)
    assert request.bars == 4
    assert request.seed == 11


def test_harmonic_reference_clip_holds_one_root_per_chord_on_the_beat_grid():
    clip = harmonic_reference_clip(make_analysis())
    assert clip.length_ticks == 4 * 1920
    assert [(n.pitch, n.start, n.duration) for n in clip.notes] == [
        (33, 0, 1920),  # A1
        (29, 1920, 1920),  # F1
        (36, 3840, 1920),  # C2
        (31, 5760, 1920),  # G1
    ]


def test_harmonic_reference_clip_leaves_no_chord_silent():
    clip = harmonic_reference_clip(make_analysis(("Am", "N", "C", "G")))
    assert [n.start for n in clip.notes] == [0, 3840, 5760]


def test_bass_follows_the_progression_one_held_note_per_bar():
    plan = generate_bass_from_analysis(make_analysis())
    assert [(n.pitch % 12, n.start, n.duration) for n in plan.notes] == [
        (9, 0, 1920),
        (5, 1920, 1920),
        (0, 3840, 1920),
        (7, 5760, 1920),
    ]
    assert plan.metadata["generation_mode"] == "bass_line"
    assert plan.metadata["harmony_source"] == "music_analysis"
    assert plan.metadata["progression"] == "Am F C G"
    assert plan.report.warnings == ()
    assert plan.request.bpm == 92


def test_bass_pulses_every_beat_without_sustain():
    plan = generate_bass_from_analysis(make_analysis(), sustain=False)
    assert len(plan.notes) == 16
    assert [n.pitch % 12 for n in plan.notes[:5]] == [9, 9, 9, 9, 5]


def test_bass_stays_in_the_detected_key_and_warns_about_foreign_roots():
    # D# is outside A minor: the reference root gets snapped, and says so.
    plan = generate_bass_from_analysis(make_analysis(("Am", "D#", "C", "G")))
    allowed = {9, 11, 0, 2, 4, 5, 7}
    assert {n.pitch % 12 for n in plan.notes} <= allowed
    assert len(plan.report.warnings) == 1
    assert "D#" in plan.report.warnings[0]


def test_bass_is_deterministic():
    analysis = make_analysis()
    assert generate_bass_from_analysis(analysis, seed=5) == generate_bass_from_analysis(
        analysis, seed=5
    )


def test_bass_requires_at_least_one_chord():
    with pytest.raises(ValueError, match="sounding note"):
        generate_bass_from_analysis(make_analysis(("N", "N")))


def test_basic_drums_kick_one_three_snare_two_four_hats_on_eighths():
    plan = generate_drums_from_analysis(make_analysis())
    by_pitch = {
        pitch: [n.start for n in plan.notes if n.pitch == pitch]
        for pitch in (KICK_PITCH, SNARE_PITCH, HIHAT_PITCH)
    }
    bar = 1920
    assert by_pitch[KICK_PITCH] == [b * bar + o for b in range(4) for o in (0, 960)]
    assert by_pitch[SNARE_PITCH] == [b * bar + o for b in range(4) for o in (480, 1440)]
    assert by_pitch[HIHAT_PITCH] == list(range(0, 4 * bar, 240))
    assert [n.start for n in plan.notes] == sorted(n.start for n in plan.notes)
    assert plan.report.note_count == len(plan.notes) == 8 + 8 + 32
    assert plan.metadata["style"] == "basic"
    assert plan.metadata["generation_mode"] == "drum_kit"


def test_drums_follow_a_three_four_metre():
    plan = generate_drums_from_analysis(make_analysis(per_bar=3))
    snares = [n.start for n in plan.notes if n.pitch == SNARE_PITCH]
    assert snares == [480, 1920, 3360, 4800]


def test_drums_reject_an_unknown_style():
    with pytest.raises(ValueError, match="style must be one of"):
        generate_drums_from_analysis(make_analysis(), style="grunge")
    assert "basic" in DRUM_STYLES


def test_accompaniment_plans_serialize_to_payload_v1():
    accompaniment = generate_accompaniment(make_analysis())
    for plan in (accompaniment.bass, accompaniment.drums):
        validate_payload_v1(composition_to_payload(plan))


def _note_on_seconds(path):
    """Absolute seconds of every note_on, honouring the file's tempo map."""
    elapsed = 0.0
    result = []
    for message in MidiFile(path):
        elapsed += message.time
        if message.type == "note_on" and message.velocity > 0:
            result.append((elapsed, message.note))
    return result


def test_exported_accompaniment_lands_on_the_recording_beats(tmp_path):
    # A drifting performance: every beat a little longer than the last.
    periods = [0.6 + 0.004 * index for index in range(16)]
    analysis = make_analysis(first_downbeat=0.73, periods=periods)
    accompaniment = generate_accompaniment(analysis)
    exporter = MidiExporter()

    drums = exporter.export(
        accompaniment.drums, tmp_path / "drums.mid", tempo_map=accompaniment.tempo_map
    )
    bass = exporter.export(
        accompaniment.bass, tmp_path / "bass.mid", tempo_map=accompaniment.tempo_map
    )

    beats = analysis.grid.beat_times
    drum_hits = _note_on_seconds(drums)
    kicks = [t for t, note in drum_hits if note == KICK_PITCH]
    snares = [t for t, note in drum_hits if note == SNARE_PITCH]
    assert kicks == pytest.approx([beats[i] for i in range(0, 16, 2)], abs=1e-3)
    assert snares == pytest.approx([beats[i] for i in range(1, 16, 2)], abs=1e-3)
    bass_onsets = [t for t, _ in _note_on_seconds(bass)]
    assert bass_onsets == pytest.approx([beats[i] for i in (0, 4, 8, 12)], abs=1e-3)
    assert MidiFile(drums).length == pytest.approx(beats[16], abs=1e-3)


def test_export_without_tempo_map_uses_the_rounded_tempo(tmp_path):
    accompaniment = generate_accompaniment(make_analysis())
    path = MidiExporter().export(accompaniment.drums, tmp_path / "plain.mid")
    tempos = [m.tempo for m in MidiFile(path).tracks[0] if m.type == "set_tempo"]
    assert tempos == [round(60_000_000 / 92)]
