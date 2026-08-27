"""Standard-library-only configuration for the embedded bridge."""

import json
import os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 20812


def load_config(directory):
    config = {"host": DEFAULT_HOST, "port": DEFAULT_PORT}
    path = os.path.join(directory, "config.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("config.json must contain a JSON object")
        config.update(loaded)
    if config["host"] != DEFAULT_HOST:
        raise ValueError("Bridge host must be 127.0.0.1")
    port = config["port"]
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Bridge port must be between 1 and 65535")
    return config
