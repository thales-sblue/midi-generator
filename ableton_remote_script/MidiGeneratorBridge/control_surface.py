"""Ableton Control Surface that executes queued commands on Live's main thread."""

import os
import queue

import Live
from ableton.v2.control_surface import ControlSurface
from Live.Clip import MidiNoteSpecification

from .bridge_core import BridgeCommandError, BridgeDispatcher, error_response
from .config import load_config
from .socket_server import BridgeSocketServer


class LiveContext:
    """Stable access to the LOM without relying on ControlSurface conveniences."""

    def __init__(self, c_instance):
        self._c_instance = c_instance

    def application(self):
        return Live.Application.get_application()

    def song(self):
        return self._c_instance.song()


class MidiGeneratorBridge(ControlSurface):
    def __init__(self, c_instance):
        super().__init__(c_instance)
        self._command_queue = queue.Queue()
        self._dispatcher = BridgeDispatcher(
            LiveContext(c_instance), note_factory=MidiNoteSpecification
        )
        config = load_config(os.path.dirname(__file__))
        self._bridge_server = BridgeSocketServer(
            self._command_queue, config["host"], config["port"]
        )
        self._bridge_server.start()

    def update_display(self):
        super().update_display()
        for _index in range(16):
            try:
                pending = self._command_queue.get_nowait()
            except queue.Empty:
                break
            request_id = pending.request.get("request_id", "")
            try:
                response = self._dispatcher.dispatch(pending.request)
            except BridgeCommandError as error:
                response = error_response(request_id, error.code, error.message)
            except Exception as error:
                response = error_response(
                    request_id, "LIVE_API_ERROR", "Ableton Live rejected the command."
                )
            pending.respond(response)

    def disconnect(self):
        self._bridge_server.stop()
        super().disconnect()
