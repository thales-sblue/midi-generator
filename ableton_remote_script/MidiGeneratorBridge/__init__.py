"""Ableton Live entry point for MidiGeneratorBridge."""


def create_instance(c_instance):
    from .control_surface import MidiGeneratorBridge

    return MidiGeneratorBridge(c_instance)
