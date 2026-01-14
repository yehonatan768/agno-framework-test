from __future__ import annotations

from textwrap import dedent
from typing import Iterable, Optional

from agno.agent import Agent
from agno.tools.mcp import MCPTools

from src.llm import build_model
from src.orchestration.policies import EXECUTION_AGENT_INSTRUCTIONS


def build_execution_agent(
    *,
    provider: str = "ollama",
    model_id: str = "llama3:8b",
    mcp_command: str = "python -m src.mcp_servers.execution.server",
    include_tools: Optional[Iterable[str]] = None,
    exclude_tools: Optional[Iterable[str]] = None,
    show_tool_calls: bool = True,  # kept for compatibility, not used by Agent in your Agno version
) -> Agent:
    """Realtime GTFS-RT specialist (vehicle positions, trip updates, alerts)."""
    model = build_model(provider=provider, model_id=model_id)

    mcp_tools = MCPTools(
        command=mcp_command,
        include_tools=list(include_tools) if include_tools else None,
        exclude_tools=list(exclude_tools) if exclude_tools else None,
    )

    # NOTE: Do NOT pass show_tool_calls into Agent(). Your Agno version does not support it.
    return Agent(
        id="execution-agent",
        name="Execution Agent",
        role="Realtime GTFS-RT specialist (vehicle positions, trip updates, alerts).",
        model=model,
        tools=[mcp_tools],
        instructions=dedent(EXECUTION_AGENT_INSTRUCTIONS).strip(),
        markdown=True,
    )
