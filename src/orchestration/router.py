from __future__ import annotations

import os
from textwrap import dedent
from typing import Iterable, Optional

from agno.models.openai import OpenAIChat
from agno.team import Team

from src.agents import build_execution_agent, build_planning_agent
from .policies import TEAM_LEADER_INSTRUCTIONS



DELEGATION_PREAMBLE = """When you are invoked by the orchestrator, you MUST start by fetching your domain data:

- Planning Agent: call the MCP tool fetch_static(force=false) as the FIRST tool call, then proceed.
- Execution Agent: call the MCP tool fetch_realtime() as the FIRST tool call, then proceed.

Do not skip this step unless the orchestrator explicitly says to use existing local data without fetching.
"""


def build_transit_team(
    *,
    mode: str = "coordinate",
    respond_directly: bool = False,
    leader_model_id: Optional[str] = None,
    planning_include_tools: Optional[Iterable[str]] = None,
    execution_include_tools: Optional[Iterable[str]] = None,
) -> Team:
    """
    Creates a 2-agent transit team.

    mode:
      - "route": leader routes to a single best agent
      - "coordinate": leader can delegate to one or both and synthesize
      - "collaborate": both run and leader synthesizes

    respond_directly:
      - If True, the selected member responds directly (no leader synthesis).
    """
    leader_model = OpenAIChat(id=leader_model_id or os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    planning_agent = build_planning_agent(include_tools=planning_include_tools)
    planning_agent.instructions = (planning_agent.instructions or "") + "\n\n" + DELEGATION_PREAMBLE
    execution_agent = build_execution_agent(include_tools=execution_include_tools)
    execution_agent.instructions = (execution_agent.instructions or "") + "\n\n" + DELEGATION_PREAMBLE

    return Team(
        id="transit-team",
        name="Transit Orchestrator",
        model=leader_model,
        members=[planning_agent, execution_agent],
        mode=mode,
        respond_directly=respond_directly,
        instructions=dedent(TEAM_LEADER_INSTRUCTIONS).strip(),
        markdown=True,
        show_members_responses=False,
    )
