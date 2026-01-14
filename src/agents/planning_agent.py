from __future__ import annotations

import os
from textwrap import dedent
from typing import Iterable, Optional

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.mcp import MCPTools

from src.orchestration.policies import PLANNING_AGENT_INSTRUCTIONS


def build_planning_agent(
    *,
    model_id: Optional[str] = None,
    mcp_command: str = "python -m src.mcp_servers.planning.server",
    include_tools: Optional[Iterable[str]] = None,
    exclude_tools: Optional[Iterable[str]] = None,
    show_tool_calls: bool = True,
) -> Agent:
    """
    Planning agent = static-only expert.

    Connects to the Planning MCP server (static GTFS tools) over stdio.
    """
    model = OpenAIChat(id=model_id or os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    mcp_tools = MCPTools(
        command=mcp_command,
        # Tool filtering is optional; leave unset unless you know tool names exactly.
        include_tools=list(include_tools) if include_tools else None,
        exclude_tools=list(exclude_tools) if exclude_tools else None,
    )

    return Agent(
        id="planning-agent",
        name="Planning Agent",
        role="Static GTFS specialist (routes/stops/trips/shapes/calendars). No realtime.",
        model=model,
        tools=[mcp_tools],
        instructions=dedent(PLANNING_AGENT_INSTRUCTIONS).strip(),
        markdown=True,
        show_tool_calls=show_tool_calls,
    )
