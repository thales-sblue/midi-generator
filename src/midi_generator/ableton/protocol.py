"""Newline-delimited JSON protocol for the localhost Ableton bridge."""

import json
import socket
import uuid
from collections.abc import Mapping
from typing import Any

from .errors import AbletonProtocolError

MAX_MESSAGE_BYTES = 8 * 1024 * 1024


def make_request(
    command: str,
    params: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id or uuid.uuid4().hex,
        "command": command,
        "params": dict(params or {}),
    }


def encode_message(message: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            dict(message), separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AbletonProtocolError("Message is not JSON-safe.") from error
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise AbletonProtocolError("Message exceeds the protocol size limit.")
    return encoded + b"\n"


def decode_message(encoded: bytes) -> dict[str, Any]:
    if len(encoded) > MAX_MESSAGE_BYTES:
        raise AbletonProtocolError("Message exceeds the protocol size limit.")
    try:
        message = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AbletonProtocolError("Bridge returned invalid JSON.") from error
    if not isinstance(message, dict):
        raise AbletonProtocolError("Protocol message must be a JSON object.")
    return message


def receive_message(connection: socket.socket) -> dict[str, Any]:
    chunks = bytearray()
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            raise AbletonProtocolError("Bridge closed the connection before a response.")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.extend(chunk[:newline])
            return decode_message(bytes(chunks))
        chunks.extend(chunk)
        if len(chunks) > MAX_MESSAGE_BYTES:
            raise AbletonProtocolError("Message exceeds the protocol size limit.")
