from mido import MidiFile
import pytest

from midi_generator.generator import (
    BEATS_PER_BAR, TICKS_PER_BEAT, GenerationConfig, generate_midi, make_melody,
)


def test_same_seed_generates_identical_melody():
    config = GenerationConfig(120, "C", "major", 4, 42)
    assert make_melody(config) == make_melody(config)


def test_same_seed_generates_identical_midi_file(tmp_path):
    config = GenerationConfig(120, "C", "major", 4, 42)
    first = generate_midi(config, tmp_path / "first.mid")
    second = generate_midi(config, tmp_path / "second.mid")
    assert first.read_bytes() == second.read_bytes()


def test_different_seed_changes_melody():
    base = GenerationConfig(120, "C", "major", 4, 42)
    changed = GenerationConfig(120, "C", "major", 4, 43)
    assert make_melody(base) != make_melody(changed)


def test_notes_belong_to_requested_scale():
    events = make_melody(GenerationConfig(120, "D", "minor", 4, 3))
    allowed_pitch_classes = {2, 4, 5, 7, 9, 10, 0}
    assert events
    assert all(pitch % 12 in allowed_pitch_classes for _, _, pitch, _ in events)


def test_midi_length_matches_requested_bars(tmp_path):
    config = GenerationConfig(100, "A", "minor", 3, 99)
    result = generate_midi(config, tmp_path / "melody.mid")
    midi = MidiFile(result)
    assert sum(message.time for message in midi.tracks[0]) == 3 * BEATS_PER_BAR * TICKS_PER_BEAT


def test_velocity_and_pauses_are_generated():
    events = make_melody(GenerationConfig(120, "C", "major", 8, 7))
    assert len({velocity for _, _, _, velocity in events}) > 1
    assert any(next_start > start + duration for (start, duration, _, _), (next_start, _, _, _) in zip(events, events[1:]))


@pytest.mark.parametrize("config", [
    GenerationConfig(10, "C", "major", 1, 1),
    GenerationConfig(120, "H", "major", 1, 1),
    GenerationConfig(120, "C", "dorian", 1, 1),
    GenerationConfig(120, "C", "major", 0, 1),
])
def test_invalid_config_is_rejected(config):
    with pytest.raises(ValueError):
        make_melody(config)
