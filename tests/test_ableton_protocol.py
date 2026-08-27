import json
import socket
import threading
import time
from contextlib import contextmanager

import pytest

from midi_generator.ableton import (
    AbletonClient,
    AbletonCommandError,
    AbletonProtocolError,
    AbletonTimeoutError,
    AbletonUnavailableError,
)
from midi_generator.ableton.protocol import decode_message, encode_message, make_request
from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import composition_to_payload


@contextmanager
def fake_bridge(handler):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    failures = []

    def serve():
        try:
            connection, _address = server.accept()
            with connection:
                request_bytes = bytearray()
                while not request_bytes.endswith(b"\n"):
                    request_bytes.extend(connection.recv(4096))
                request = json.loads(request_bytes.decode("utf-8"))
                response = handler(request)
                if isinstance(response, bytes):
                    connection.sendall(response)
                else:
                    connection.sendall(encode_message(response))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:  # surfaced after the context exits
            failures.append(error)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert not failures


def test_protocol_serialization_and_newline_framing():
    request = make_request("ping", {}, request_id="request-1")

    encoded = encode_message(request)

    assert encoded.endswith(b"\n")
    assert decode_message(encoded[:-1]) == request


def test_client_ping_and_request_id_correlation():
    def respond(request):
        return {
            "request_id": request["request_id"],
            "ok": True,
            "result": {"application": "Ableton Live", "bridge": "MidiGeneratorBridge"},
        }

    with fake_bridge(respond) as port:
        result = AbletonClient(port=port).ping()

    assert result["application"] == "Ableton Live"


def test_client_rejects_mismatched_request_id():
    def respond(_request):
        return {"request_id": "wrong", "ok": True, "result": {}}

    with fake_bridge(respond) as port:
        with pytest.raises(AbletonProtocolError, match="request_id"):
            AbletonClient(port=port).ping()


def test_client_reports_timeout():
    def respond(request):
        time.sleep(0.15)
        return {"request_id": request["request_id"], "ok": True, "result": {}}

    with fake_bridge(respond) as port:
        with pytest.raises(AbletonTimeoutError, match="timed out"):
            AbletonClient(port=port, timeout=0.03).ping()


def test_client_reports_connection_refused(monkeypatch):
    def refuse_connection(*_args, **_kwargs):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(socket, "create_connection", refuse_connection)

    with pytest.raises(AbletonUnavailableError, match="unavailable"):
        AbletonClient(timeout=0.1).ping()


def test_client_rejects_invalid_json_response():
    with fake_bridge(lambda _request: b"not-json\n") as port:
        with pytest.raises(AbletonProtocolError, match="invalid JSON"):
            AbletonClient(port=port).ping()


def test_client_raises_specific_bridge_command_error():
    def respond(request):
        return {
            "request_id": request["request_id"],
            "ok": False,
            "error": {"code": "TRACK_NOT_FOUND", "message": "No such track."},
        }

    with fake_bridge(respond) as port:
        with pytest.raises(AbletonCommandError) as caught:
            AbletonClient(port=port).get_session_state()

    assert caught.value.code == "TRACK_NOT_FOUND"
    assert caught.value.message == "No such track."


def test_client_only_accepts_loopback_endpoint():
    with pytest.raises(ValueError, match="127.0.0.1"):
        AbletonClient(host="0.0.0.0")


def test_create_midi_clip_sends_exact_integration_payload():
    payload = composition_to_payload(
        generate_plan(MelodyRequest(120, "C", "minor", 4, 42))
    )
    captured = []

    def respond(request):
        captured.append(request)
        return {
            "request_id": request["request_id"],
            "ok": True,
            "result": {
                "inserted": True,
                "track_index": 0,
                "scene_index": 0,
                "clip_length_beats": 16.0,
                "note_count": len(payload["notes"]),
                "schema_version": 1,
            },
        }

    with fake_bridge(respond) as port:
        result = AbletonClient(port=port).create_midi_clip(0, 0, payload)

    assert captured[0]["command"] == "create_midi_clip"
    assert captured[0]["params"] == {
        "track_index": 0,
        "scene_index": 0,
        "payload": payload,
    }
    assert result["inserted"] is True
