"""Background loopback JSON-lines server; never touches the Live API."""

import json
import queue
import socket
import threading

from .bridge_core import BridgeCommandError, error_response, validate_request

MAX_MESSAGE_BYTES = 8 * 1024 * 1024


class PendingCommand:
    def __init__(self, request):
        self.request = request
        self._response = queue.Queue(maxsize=1)

    def respond(self, response):
        self._response.put(response)

    def wait(self, timeout):
        return self._response.get(timeout=timeout)


class BridgeSocketServer:
    def __init__(self, command_queue, host, port, response_timeout=10.0):
        if host != "127.0.0.1":
            raise ValueError("BridgeSocketServer only binds to 127.0.0.1")
        self._command_queue = command_queue
        self._host = host
        self._port = port
        self._response_timeout = response_timeout
        self._stop_event = threading.Event()
        self._socket = None
        self._thread = None

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self._host, self._port))
        server.listen(4)
        server.settimeout(0.5)
        self._socket = server
        self._port = server.getsockname()[1]
        self._thread = threading.Thread(
            target=self._run, name="MidiGeneratorBridgeSocket", daemon=True
        )
        self._thread.start()

    @property
    def port(self):
        return self._port

    def stop(self):
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self):
        server = self._socket
        while not self._stop_event.is_set():
            try:
                connection, _address = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(5.0)
                self._handle_connection(connection)

    def _handle_connection(self, connection):
        request_id = ""
        try:
            request = _receive_json_line(connection)
            if isinstance(request, dict) and isinstance(request.get("request_id"), str):
                request_id = request["request_id"]
            validate_request(request)
            pending = PendingCommand(request)
            self._command_queue.put(pending)
            response = pending.wait(self._response_timeout)
        except BridgeCommandError as error:
            response = error_response(request_id, error.code, error.message)
        except queue.Empty:
            response = error_response(
                request_id, "BRIDGE_TIMEOUT", "Live main thread did not answer in time."
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            response = error_response(request_id, "INVALID_REQUEST", str(error))
        try:
            encoded = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
            connection.sendall(encoded)
        except OSError:
            pass


def _receive_json_line(connection):
    chunks = bytearray()
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            raise ValueError("Connection closed before newline")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.extend(chunk[:newline])
            return json.loads(chunks.decode("utf-8"))
        chunks.extend(chunk)
        if len(chunks) > MAX_MESSAGE_BYTES:
            raise ValueError("Message exceeds size limit")
