"""Small synchronous client for the localhost Ableton Remote Script bridge."""

import socket
from typing import Any

from midi_generator.integration import IntegrationPayload, validate_payload_v1

from .config import DEFAULT_HOST, configured_port, validate_endpoint
from .errors import (
    AbletonCommandError,
    AbletonProtocolError,
    AbletonTimeoutError,
    AbletonUnavailableError,
)
from .protocol import encode_message, make_request, receive_message


class AbletonClient:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int | None = None,
        timeout: float = 3.0,
    ) -> None:
        resolved_port = configured_port() if port is None else port
        validate_endpoint(host, resolved_port)
        if timeout <= 0:
            raise ValueError("Ableton bridge timeout must be positive.")
        self.host = host
        self.port = resolved_port
        self.timeout = timeout

    def ping(self) -> dict[str, Any]:
        return self._call("ping", {})

    def get_session_state(self) -> dict[str, Any]:
        return self._call("get_session_state", {})

    def create_midi_clip(
        self,
        track_index: int,
        scene_index: int,
        payload: IntegrationPayload,
    ) -> dict[str, Any]:
        validate_payload_v1(payload)
        return self._call(
            "create_midi_clip",
            {
                "track_index": track_index,
                "scene_index": scene_index,
                "payload": payload,
            },
        )

    def get_midi_clip(self, track_index: int, scene_index: int) -> dict[str, Any]:
        return self._call(
            "get_midi_clip",
            {"track_index": track_index, "scene_index": scene_index},
        )

    def replace_midi_clip_notes(
        self,
        track_index: int,
        scene_index: int,
        expected_fingerprint: str,
        notes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._call(
            "replace_midi_clip_notes",
            {
                "track_index": track_index,
                "scene_index": scene_index,
                "expected_fingerprint": expected_fingerprint,
                "notes": notes,
            },
        )

    def duplicate_midi_clip(
        self,
        source_track_index: int,
        source_scene_index: int,
        target_track_index: int,
        target_scene_index: int,
        expected_source_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "source_track_index": source_track_index,
            "source_scene_index": source_scene_index,
            "target_track_index": target_track_index,
            "target_scene_index": target_scene_index,
        }
        if expected_source_fingerprint is not None:
            params["expected_source_fingerprint"] = expected_source_fingerprint
        return self._call(
            "duplicate_midi_clip",
            params,
        )

    def _call(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        request = make_request(command, params)
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            ) as connection:
                connection.settimeout(self.timeout)
                connection.sendall(encode_message(request))
                response = receive_message(connection)
        except socket.timeout as error:
            raise AbletonTimeoutError(
                f"Ableton bridge timed out at {self.host}:{self.port}."
            ) from error
        except OSError as error:
            raise AbletonUnavailableError(
                f"Ableton bridge unavailable at {self.host}:{self.port}: {error}"
            ) from error

        return self._validate_response(request["request_id"], response)

    @staticmethod
    def _validate_response(
        request_id: str, response: dict[str, Any]
    ) -> dict[str, Any]:
        if response.get("request_id") != request_id:
            raise AbletonProtocolError("Bridge response request_id does not match.")
        if not isinstance(response.get("ok"), bool):
            raise AbletonProtocolError("Bridge response must contain boolean ok.")
        if response["ok"]:
            result = response.get("result")
            if not isinstance(result, dict):
                raise AbletonProtocolError("Successful bridge response needs an object result.")
            return result

        error = response.get("error")
        if not isinstance(error, dict):
            raise AbletonProtocolError("Failed bridge response needs an error object.")
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            raise AbletonProtocolError("Bridge error needs string code and message.")
        raise AbletonCommandError(code, message)
