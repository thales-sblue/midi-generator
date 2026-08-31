"""Mido-backed MIDI file exporter."""

from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from midi_generator.domain import CompositionPlan
from midi_generator.generation.melody import TICKS_PER_BEAT


class MidiExporter:
    """Writes a composition plan as a standard single-track MIDI file."""

    def export(self, plan: CompositionPlan, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        midi = MidiFile(ticks_per_beat=TICKS_PER_BEAT)
        track = MidiTrack()
        midi.tracks.append(track)
        track.append(MetaMessage("track_name", name="Generated Melody", time=0))
        track.append(MetaMessage("set_tempo", tempo=bpm2tempo(plan.request.bpm), time=0))
        track.append(
            MetaMessage(
                "time_signature",
                numerator=plan.request.time_signature.numerator,
                denominator=plan.request.time_signature.denominator,
                time=0,
            )
        )
        track.append(Message("program_change", program=0, channel=0, time=0))

        cursor = 0
        for note in plan.notes:
            track.append(Message("note_on", note=note.pitch, velocity=note.velocity, channel=note.channel, time=note.start - cursor))
            track.append(Message("note_off", note=note.pitch, velocity=0, channel=note.channel, time=note.duration))
            cursor = note.start + note.duration
        track.append(MetaMessage("end_of_track", time=plan.total_duration_ticks - cursor))
        midi.save(destination)
        return destination
