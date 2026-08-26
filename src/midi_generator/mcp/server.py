"""MCP server exposing the existing deterministic composition engine."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import IntegrationPayload, composition_to_payload

mcp = MCPServer(
    "midi-generator",
    description="Deterministic melody generation exposed as Integration Payload v1.",
    version="1.0.0",
)


@mcp.tool()
def generate_melody(
    bpm: int,
    root_note: str,
    scale: str,
    bars: int,
    seed: int,
) -> IntegrationPayload:
    """Generate a deterministic melody and return Integration Payload v1."""
    request = MelodyRequest(
        bpm=bpm,
        root_note=root_note,
        scale=scale,
        bars=bars,
        seed=seed,
    )
    try:
        plan = generate_plan(request)
    except ValueError as error:
        raise ToolError(str(error)) from error
    return composition_to_payload(plan)


def main() -> None:
    """Run the local MCP server over the default stdio transport."""
    mcp.run(transport="stdio")
