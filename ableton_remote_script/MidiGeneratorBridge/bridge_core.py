"""Live-facing commands with no dependency on pip-installed packages."""

import hashlib
import json

SCHEMA_VERSION = 1
SUPPORTED_TIME_SIGNATURE = "4/4"
BRIDGE_NAME = "MidiGeneratorBridge"
FLOAT_PRECISION = 9
NOTE_END_TOLERANCE = 1e-9


class BridgeCommandError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def success_response(request_id, result):
    return {"request_id": request_id, "ok": True, "result": result}


def error_response(request_id, code, message):
    return {
        "request_id": request_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }


def validate_request(request):
    if not isinstance(request, dict):
        raise BridgeCommandError("INVALID_REQUEST", "Request must be a JSON object.")
    request_id = request.get("request_id")
    command = request.get("command")
    params = request.get("params")
    if not isinstance(request_id, str) or not request_id:
        raise BridgeCommandError("INVALID_REQUEST", "request_id must be a string.")
    if not isinstance(command, str) or not command:
        raise BridgeCommandError("INVALID_REQUEST", "command must be a string.")
    if not isinstance(params, dict):
        raise BridgeCommandError("INVALID_REQUEST", "params must be an object.")
    return request_id, command, params


def payload_to_clip_data(payload):
    if not isinstance(payload, dict):
        raise BridgeCommandError("INVALID_PAYLOAD", "payload must be an object.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise BridgeCommandError(
            "UNSUPPORTED_SCHEMA", "Only Integration Payload schema_version 1 is supported."
        )
    if payload.get("time_signature") != SUPPORTED_TIME_SIGNATURE:
        raise BridgeCommandError(
            "UNSUPPORTED_TIME_SIGNATURE", "Only time_signature 4/4 is supported."
        )
    ticks_per_beat = payload.get("ticks_per_beat")
    total_ticks = payload.get("total_duration_ticks")
    if not _positive_number(ticks_per_beat):
        raise BridgeCommandError(
            "INVALID_PAYLOAD", "ticks_per_beat must be positive."
        )
    if not _positive_number(total_ticks):
        raise BridgeCommandError(
            "INVALID_PAYLOAD", "total_duration_ticks must be positive."
        )
    source_notes = payload.get("notes")
    if not isinstance(source_notes, list):
        raise BridgeCommandError("INVALID_PAYLOAD", "notes must be a list.")

    notes = []
    for index, note in enumerate(source_notes):
        if not isinstance(note, dict):
            raise BridgeCommandError(
                "INVALID_PAYLOAD", "Note {} must be an object.".format(index)
            )
        try:
            pitch = note["pitch"]
            start = note["start"]
            duration = note["duration"]
            velocity = note["velocity"]
        except KeyError as error:
            raise BridgeCommandError(
                "INVALID_PAYLOAD",
                "Note {} is missing {}.".format(index, error.args[0]),
            )
        if not _integer_between(pitch, 0, 127):
            raise BridgeCommandError("INVALID_PAYLOAD", "Invalid note pitch.")
        if not _integer_between(velocity, 1, 127):
            raise BridgeCommandError("INVALID_PAYLOAD", "Invalid note velocity.")
        if not _non_negative_number(start) or not _positive_number(duration):
            raise BridgeCommandError("INVALID_PAYLOAD", "Invalid note timing.")
        notes.append(
            {
                "pitch": pitch,
                "start_time": float(start) / ticks_per_beat,
                "duration": float(duration) / ticks_per_beat,
                "velocity": velocity,
                "mute": False,
            }
        )

    return {
        "clip_length_beats": float(total_ticks) / ticks_per_beat,
        "notes": notes,
    }


class BridgeDispatcher:
    def __init__(self, live_context, note_factory=None):
        self._live = live_context
        self._note_factory = note_factory or _dictionary_note_factory

    def dispatch(self, request):
        request_id, command, params = validate_request(request)
        if command == "ping":
            result = self._ping()
        elif command == "get_session_state":
            result = self._get_session_state()
        elif command == "create_midi_clip":
            result = self._create_midi_clip(params)
        elif command == "get_midi_clip":
            result = self._get_midi_clip(params)
        elif command == "replace_midi_clip_notes":
            result = self._replace_midi_clip_notes(params)
        elif command == "duplicate_midi_clip":
            result = self._duplicate_midi_clip(params)
        else:
            raise BridgeCommandError(
                "UNKNOWN_COMMAND", "Unknown command: {}".format(command)
            )
        return success_response(request_id, result)

    def _ping(self):
        application = self._live.application()
        result = {"application": "Ableton Live", "bridge": BRIDGE_NAME}
        version = application.get_version_string()
        if version:
            result["version"] = str(version)
        return result

    def _get_session_state(self):
        song = self._live.song()
        tracks = [
            {
                "index": index,
                "name": str(track.name),
                "can_hold_midi": bool(track.has_midi_input),
            }
            for index, track in enumerate(song.tracks)
        ]
        scenes = [
            {"index": index, "name": str(scene.name)}
            for index, scene in enumerate(song.scenes)
        ]
        return {"tracks": tracks, "scenes": scenes}

    def _create_midi_clip(self, params):
        track_index = _required_index(params, "track_index")
        scene_index = _required_index(params, "scene_index")
        payload = params.get("payload")
        clip_data = payload_to_clip_data(payload)
        song = self._live.song()
        if track_index >= len(song.tracks):
            raise BridgeCommandError("TRACK_NOT_FOUND", "Track index does not exist.")
        if scene_index >= len(song.scenes):
            raise BridgeCommandError("SCENE_NOT_FOUND", "Scene index does not exist.")
        track = song.tracks[track_index]
        if not bool(track.has_midi_input):
            raise BridgeCommandError(
                "TRACK_NOT_MIDI", "Target track cannot hold MIDI clips."
            )
        if scene_index >= len(track.clip_slots):
            raise BridgeCommandError("SCENE_NOT_FOUND", "Track has no such clip slot.")
        clip_slot = track.clip_slots[scene_index]
        if bool(clip_slot.has_clip):
            raise BridgeCommandError(
                "TARGET_CLIP_SLOT_NOT_EMPTY", "Target clip slot already contains a clip."
            )

        clip_slot.create_clip(clip_data["clip_length_beats"])
        live_notes = tuple(self._note_factory(**note) for note in clip_data["notes"])
        if live_notes:
            clip_slot.clip.add_new_notes(live_notes)
        return {
            "inserted": True,
            "track_index": track_index,
            "scene_index": scene_index,
            "clip_length_beats": clip_data["clip_length_beats"],
            "note_count": len(clip_data["notes"]),
            "schema_version": SCHEMA_VERSION,
        }

    def _get_midi_clip(self, params):
        track_index = _required_index(params, "track_index")
        scene_index = _required_index(params, "scene_index")
        clip = self._require_midi_clip(track_index, scene_index)
        return _clip_snapshot(clip, track_index, scene_index)

    def _replace_midi_clip_notes(self, params):
        track_index = _required_index(params, "track_index")
        scene_index = _required_index(params, "scene_index")
        expected = params.get("expected_fingerprint")
        if not isinstance(expected, str) or not expected:
            raise BridgeCommandError(
                "INVALID_REQUEST", "expected_fingerprint must be a non-empty string."
            )
        clip = self._require_midi_clip(track_index, scene_index)
        current = _clip_snapshot(clip, track_index, scene_index)
        if expected != current["clip_fingerprint"]:
            raise BridgeCommandError(
                "CLIP_CHANGED",
                "The MIDI clip changed since it was read. Read it again before editing.",
            )
        notes = _validated_notes(params.get("notes"), current["clip_length_beats"])

        # Every possible request error has been checked before this first mutation.
        clip.remove_notes_extended(0, 128, 0.0, current["clip_length_beats"])
        live_notes = tuple(self._note_factory(**note) for note in notes)
        if live_notes:
            clip.add_new_notes(live_notes)
        updated = _clip_snapshot(clip, track_index, scene_index)
        return {
            "replaced": True,
            "track_index": track_index,
            "scene_index": scene_index,
            "clip_length_beats": updated["clip_length_beats"],
            "note_count": len(updated["notes"]),
            "clip_fingerprint": updated["clip_fingerprint"],
        }

    def _duplicate_midi_clip(self, params):
        source_track_index = _required_index(params, "source_track_index")
        source_scene_index = _required_index(params, "source_scene_index")
        target_track_index = _required_index(params, "target_track_index")
        target_scene_index = _required_index(params, "target_scene_index")
        source = self._require_midi_clip(source_track_index, source_scene_index)
        source_data = _clip_snapshot(
            source, source_track_index, source_scene_index
        )
        if "expected_source_fingerprint" in params:
            expected = params["expected_source_fingerprint"]
            if not isinstance(expected, str) or not expected:
                raise BridgeCommandError(
                    "INVALID_REQUEST",
                    "expected_source_fingerprint must be a non-empty string.",
                )
            if expected != source_data["clip_fingerprint"]:
                raise BridgeCommandError(
                    "CLIP_CHANGED",
                    "The source MIDI clip changed since it was read. Read it again before duplicating.",
                )
        target_slot = self._require_empty_midi_slot(
            target_track_index, target_scene_index
        )

        target_slot.create_clip(source_data["clip_length_beats"])
        target = target_slot.clip
        target.name = source_data["name"]
        target.looping = source_data["looping"]
        live_notes = tuple(
            self._note_factory(**note) for note in source_data["notes"]
        )
        if live_notes:
            target.add_new_notes(live_notes)
        result = _clip_snapshot(target, target_track_index, target_scene_index)
        result["duplicated"] = True
        result["source_track_index"] = source_track_index
        result["source_scene_index"] = source_scene_index
        return result

    def _require_midi_clip(self, track_index, scene_index):
        slot = self._require_slot(track_index, scene_index)
        if not bool(slot.has_clip):
            raise BridgeCommandError("CLIP_NOT_FOUND", "Clip slot is empty.")
        clip = slot.clip
        if not bool(clip.is_midi_clip):
            raise BridgeCommandError("CLIP_NOT_MIDI", "Clip is not a MIDI clip.")
        return clip

    def _require_empty_midi_slot(self, track_index, scene_index):
        slot = self._require_slot(track_index, scene_index)
        if bool(slot.has_clip):
            raise BridgeCommandError(
                "TARGET_CLIP_SLOT_NOT_EMPTY", "Target clip slot already contains a clip."
            )
        return slot

    def _require_slot(self, track_index, scene_index):
        song = self._live.song()
        if track_index >= len(song.tracks):
            raise BridgeCommandError("TRACK_NOT_FOUND", "Track index does not exist.")
        if scene_index >= len(song.scenes):
            raise BridgeCommandError("SCENE_NOT_FOUND", "Scene index does not exist.")
        track = song.tracks[track_index]
        if not bool(track.has_midi_input):
            raise BridgeCommandError("TRACK_NOT_MIDI", "Track cannot hold MIDI clips.")
        if scene_index >= len(track.clip_slots):
            raise BridgeCommandError("SCENE_NOT_FOUND", "Track has no such clip slot.")
        return track.clip_slots[scene_index]


def _clip_snapshot(clip, track_index, scene_index):
    length = _normalized_float(clip.length)
    notes = [_note_to_dict(note) for note in clip.get_notes_extended(0, 128, 0.0, length)]
    notes.sort(key=lambda note: (note["start_time"], note["pitch"], note["duration"]))
    result = {
        "track_index": track_index,
        "scene_index": scene_index,
        "name": str(clip.name),
        "clip_length_beats": length,
        "looping": bool(clip.looping),
        "notes": notes,
    }
    result["clip_fingerprint"] = _clip_fingerprint(length, notes)
    return result


def _note_to_dict(note):
    return {
        "pitch": int(note.pitch),
        "start_time": _normalized_float(note.start_time),
        "duration": _normalized_float(note.duration),
        "velocity": int(note.velocity),
        "mute": bool(note.mute),
    }


def _validated_notes(value, clip_length):
    if not isinstance(value, list):
        raise BridgeCommandError("INVALID_REQUEST", "notes must be a list.")
    notes = []
    for index, note in enumerate(value):
        if not isinstance(note, dict):
            raise BridgeCommandError(
                "INVALID_NOTE", "Note {} must be an object.".format(index)
            )
        required = ("pitch", "start_time", "duration", "velocity", "mute")
        missing = [name for name in required if name not in note]
        if missing:
            raise BridgeCommandError(
                "INVALID_NOTE",
                "Note {} is missing {}.".format(index, missing[0]),
            )
        if not _integer_between(note["pitch"], 0, 127):
            raise BridgeCommandError("INVALID_NOTE", "Note pitch must be 0..127.")
        if not _non_negative_number(note["start_time"]):
            raise BridgeCommandError("INVALID_NOTE", "Note start_time must be non-negative.")
        if not _positive_number(note["duration"]):
            raise BridgeCommandError("INVALID_NOTE", "Note duration must be positive.")
        if not _integer_between(note["velocity"], 1, 127):
            raise BridgeCommandError("INVALID_NOTE", "Note velocity must be 1..127.")
        if not isinstance(note["mute"], bool):
            raise BridgeCommandError("INVALID_NOTE", "Note mute must be boolean.")
        start = _normalized_float(note["start_time"])
        duration = _normalized_float(note["duration"])
        if start + duration > clip_length + NOTE_END_TOLERANCE:
            raise BridgeCommandError(
                "NOTE_OUTSIDE_CLIP", "A note extends beyond the clip length."
            )
        notes.append(
            {
                "pitch": note["pitch"],
                "start_time": start,
                "duration": duration,
                "velocity": note["velocity"],
                "mute": note["mute"],
            }
        )
    return notes


def _clip_fingerprint(clip_length, notes):
    canonical = json.dumps(
        {"clip_length_beats": _normalized_float(clip_length), "notes": notes},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _normalized_float(value):
    return round(float(value), FLOAT_PRECISION)


def _required_index(params, name):
    value = params.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BridgeCommandError(
            "INVALID_REQUEST", "{} must be a non-negative integer.".format(name)
        )
    return value


def _positive_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value > 0
    )


def _non_negative_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value >= 0
    )


def _integer_between(value, minimum, maximum):
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and minimum <= value <= maximum
    )


def _dictionary_note_factory(**note):
    return note
