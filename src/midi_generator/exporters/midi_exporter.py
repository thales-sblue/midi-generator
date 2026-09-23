"""Mido-backed MIDI file exporter."""

from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from midi_generator.domain import CompositionPlan, MidiTempoMap
from midi_generator.generation.melody import TICKS_PER_BEAT

# Events sharing a tick are written tempo first, then note-offs, then
# note-ons, so a note ending where the next begins is released before it
# retriggers.
_TEMPO, _NOTE_OFF, _NOTE_ON = 0, 1, 2


class MidiExporter:
    """Writes a composition plan as a standard single-track MIDI file."""

    def export(
        self,
        plan: CompositionPlan,
        destination: str | Path,
        *,
        tempo_map: MidiTempoMap | None = None,
    ) -> Path:
        """Write ``plan`` to ``destination``.

        Without ``tempo_map`` the file plays at the plan's constant BPM from
        tick 0. With one, the plan is shifted by its lead-in and every tempo
        change is written, so the file follows the timeline of the recording
        the map was taken from.
        """
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        midi = MidiFile(ticks_per_beat=TICKS_PER_BEAT)
        track = MidiTrack()
        midi.tracks.append(track)

        offset = 0
        tempo_events: list[tuple[int, int]] = [(0, bpm2tempo(plan.request.bpm))]
        if tempo_map is not None:
            offset = tempo_map.lead_in_ticks
            tempo_events = [
                (change.tick, change.microseconds_per_beat)
                for change in tempo_map.changes
            ]

        track.append(MetaMessage("track_name", name="Generated Melody", time=0))
        first_tick, first_tempo = tempo_events[0]
        track.append(MetaMessage("set_tempo", tempo=first_tempo, time=0))
        track.append(
            MetaMessage(
                "time_signature",
                numerator=plan.request.time_signature.numerator,
                denominator=plan.request.time_signature.denominator,
                time=0,
            )
        )
        track.append(Message("program_change", program=0, channel=0, time=0))

        events: list[tuple[int, int, int, Message | MetaMessage]] = []
        for tick, tempo in tempo_events[1:] if first_tick == 0 else tempo_events:
            events.append((tick, _TEMPO, len(events), MetaMessage("set_tempo", tempo=tempo)))
        for note in plan.notes:
            start = note.start + offset
            events.append(
                (
                    start,
                    _NOTE_ON,
                    len(events),
                    Message("note_on", note=note.pitch, velocity=note.velocity, channel=note.channel),
                )
            )
            events.append(
                (
                    start + note.duration,
                    _NOTE_OFF,
                    len(events),
                    Message("note_off", note=note.pitch, velocity=0, channel=note.channel),
                )
            )
        events.sort(key=lambda event: event[:3])

        cursor = 0
        for tick, _, _, message in events:
            track.append(message.copy(time=tick - cursor))
            cursor = tick
        track.append(
            MetaMessage("end_of_track", time=offset + plan.total_duration_ticks - cursor)
        )
        midi.save(destination)
        return destination
