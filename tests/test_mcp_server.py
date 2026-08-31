import asyncio
import ast
import json
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.server.mcpserver.exceptions import ToolError

from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import composition_to_payload
from midi_generator.mcp.server import generate_melody, mcp


VALID_ARGUMENTS = {
    "bpm": 120,
    "root_note": "C",
    "scale": "minor",
    "bars": 4,
    "seed": 42,
}


def test_tool_handler_builds_request_and_reuses_engine(monkeypatch):
    expected_request = MelodyRequest(**VALID_ARGUMENTS)
    expected_plan = generate_plan(expected_request)
    captured = []

    def fake_generate_plan(request):
        captured.append(request)
        return expected_plan

    monkeypatch.setattr("midi_generator.mcp.server.generate_plan", fake_generate_plan)

    payload = generate_melody(**VALID_ARGUMENTS)

    assert captured == [expected_request]
    assert payload == composition_to_payload(expected_plan)


def test_tool_handler_returns_complete_json_safe_v1_payload():
    payload = generate_melody(**VALID_ARGUMENTS)
    plan = generate_plan(MelodyRequest(**VALID_ARGUMENTS))

    assert payload["schema_version"] == 1
    assert payload["time_signature"] == "4/4"
    assert payload["ticks_per_beat"] == 480
    assert len(payload["notes"]) == len(plan.notes)
    assert payload["notes"] == composition_to_payload(plan)["notes"]
    assert json.loads(json.dumps(payload)) == payload


def test_tool_handler_is_deterministic_for_same_input_and_seed():
    assert generate_melody(**VALID_ARGUMENTS) == generate_melody(**VALID_ARGUMENTS)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("bpm", 10, "BPM must be between 20 and 400"),
        ("root_note", "H", "Root note must be"),
        ("scale", "wurlitzer", "Scale must be one of"),
        ("bars", 0, "Bars must be at least 1"),
    ],
)
def test_tool_handler_rejects_invalid_input(field, value, message):
    arguments = VALID_ARGUMENTS | {field: value}

    with pytest.raises(ToolError, match=message):
        generate_melody(**arguments)


def test_tool_handler_does_not_silence_unexpected_exceptions(monkeypatch):
    def fail_unexpectedly(request):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr("midi_generator.mcp.server.generate_plan", fail_unexpectedly)

    with pytest.raises(RuntimeError, match="unexpected failure"):
        generate_melody(**VALID_ARGUMENTS)


def test_real_mcp_client_receives_structured_payload_v1():
    async def call_tool():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool("generate_melody", VALID_ARGUMENTS)
            return tools, result

    tools, result = asyncio.run(call_tool())

    tool_names = {tool.name for tool in tools.tools}
    assert "get_ableton_session" in tool_names
    assert "generate_and_insert_melody" in tool_names
    assert "transform_ableton_midi_clip" in tool_names
    assert "analyze_ableton_midi_clip" in tool_names
    assert "generate_contextual_melody_from_ableton_clip" in tool_names
    assert "create_contextual_variation_from_ableton_clip" in tool_names
    tool = next(tool for tool in tools.tools if tool.name == "generate_melody")
    assert tool.output_schema is not None
    assert "time_signature" in tool.output_schema["required"]
    assert "ticks_per_beat" in tool.output_schema["required"]
    assert result.is_error is False
    assert result.structured_content == generate_melody(**VALID_ARGUMENTS)
    assert result.structured_content["schema_version"] == 1


def test_real_mcp_client_reports_engine_validation_error():
    async def call_tool():
        async with Client(mcp) as client:
            return await client.call_tool(
                "generate_melody", VALID_ARGUMENTS | {"root_note": "H"}
            )

    result = asyncio.run(call_tool())

    assert result.is_error is True
    assert result.structured_content is None
    assert "Root note must be" in result.content[0].text


def test_real_stdio_process_exposes_deterministic_payload_and_errors():
    project_root = Path(__file__).parents[1]
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "midi_generator.mcp"],
        env={"PYTHONPATH": str(project_root / "src")},
        cwd=project_root,
    )

    async def exercise_server():
        async with Client(parameters, read_timeout_seconds=10) as client:
            tools = await client.list_tools()
            first = await client.call_tool("generate_melody", VALID_ARGUMENTS)
            second = await client.call_tool("generate_melody", VALID_ARGUMENTS)
            invalid = await client.call_tool(
                "generate_melody", VALID_ARGUMENTS | {"root_note": "H"}
            )
            return tools, first, second, invalid

    tools, first, second, invalid = asyncio.run(
        asyncio.wait_for(exercise_server(), timeout=20)
    )

    assert any(tool.name == "generate_melody" for tool in tools.tools)
    assert any(tool.name == "transform_ableton_midi_clip" for tool in tools.tools)
    assert first.is_error is False
    assert first.structured_content is not None
    assert first.structured_content["schema_version"] == 1
    assert first.structured_content["time_signature"] == "4/4"
    assert first.structured_content["ticks_per_beat"] == 480
    assert first.structured_content["notes"]
    assert second.structured_content == first.structured_content
    assert invalid.is_error is True
    assert "Root note must be" in invalid.content[0].text


def _import_roots(paths):
    roots = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_core_and_integration_layers_preserve_dependency_boundaries():
    source_root = Path(__file__).parents[1] / "src" / "midi_generator"
    domain_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (source_root / "domain").glob("*.py")
    )
    generation_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (source_root / "generation").glob("*.py")
    )
    integration_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (source_root / "integration").glob("*.py")
    )
    domain_imports = _import_roots((source_root / "domain").glob("*.py"))
    generation_imports = _import_roots((source_root / "generation").glob("*.py"))
    integration_imports = _import_roots((source_root / "integration").glob("*.py"))

    assert {"mcp", "mido", "ableton"}.isdisjoint(domain_imports)
    assert {"mcp", "mido", "ableton"}.isdisjoint(generation_imports)
    assert {"mcp", "ableton"}.isdisjoint(integration_imports)
    assert "midi_generator.ableton" not in domain_source
    assert "midi_generator.ableton" not in generation_source
    assert "midi_generator.ableton" not in integration_source


def test_mcp_layer_contains_no_musical_generation_rules():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "midi_generator"
        / "mcp"
        / "server.py"
    ).read_text(encoding="utf-8")

    assert "random" not in source
    assert "mido" not in source
    assert "ROOT_NOTES" not in source
    assert "SCALE_INTERVALS" not in source
    assert "generate_plan(request)" in source
    assert "composition_to_payload" in source


def test_transformations_are_independent_and_use_only_seeded_random():
    root = Path(__file__).parents[1] / "src" / "midi_generator" / "transformations"
    paths = tuple(root.glob("*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    imports = _import_roots(paths)

    assert {"mcp", "mido", "ableton", "Live"}.isdisjoint(imports)
    assert "random.Random(seed)" in source
    assert "random.randint" not in source


def test_remote_script_contains_no_transformation_algorithms():
    root = Path(__file__).parents[1] / "ableton_remote_script" / "MidiGeneratorBridge"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    assert "transpose" not in source
    assert "invert" not in source
    assert "retrograde" not in source
    assert "legato" not in source
    assert "staccato" not in source
    assert "quantize" not in source
    assert "humanize" not in source
    assert "random" not in source
