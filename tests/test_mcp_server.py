import asyncio
import json
from pathlib import Path

import pytest
from mcp import Client
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
        ("scale", "dorian", "Scale must be 'major' or 'minor'"),
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

    tool = next(tool for tool in tools.tools if tool.name == "generate_melody")
    assert tool.output_schema is not None
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


def test_core_layers_do_not_depend_on_mcp():
    source_root = Path(__file__).parents[1] / "src" / "midi_generator"
    core_files = list((source_root / "domain").glob("*.py")) + list(
        (source_root / "generation").glob("*.py")
    )

    assert core_files
    assert all("mcp" not in path.read_text(encoding="utf-8") for path in core_files)


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
