from __future__ import annotations

from textwrap import dedent
from typing import Iterable, Optional

from agno.team import Team

from src.llm import build_model
from src.agents import build_execution_agent, build_planning_agent
from .policies import TEAM_LEADER_INSTRUCTIONS


DELEGATION_PREAMBLE = """\
When you are invoked by the orchestrator, you MUST start by fetching your domain data:

- Planning Agent: call the MCP tool fetch_static(force=false) as the FIRST tool call, then proceed.
- Execution Agent: call the MCP tool fetch_realtime() as the FIRST tool call, then proceed.

Do not skip this step unless the orchestrator explicitly says to use existing local data without fetching.
"""


def build_transit_team(
    *,
    mode: str = "coordinate",  # kept for compatibility with your CLI/settings (not used by this Agno version)
    respond_directly: bool = False,  # kept for compatibility (not used by this Agno version)
    leader_provider: str = "ollama",
    leader_model_id: str = "llama3.1:8b",
    planning_provider: str = "ollama",
    planning_model_id: str = "llama3.1:8b",
    execution_provider: str = "ollama",
    execution_model_id: str = "llama3.1:8b",
    planning_include_tools: Optional[Iterable[str]] = None,
    execution_include_tools: Optional[Iterable[str]] = None,
) -> Team:
    """
    Creates a 2-agent transit team.

    NOTE:
    Your installed Agno Team API does not support `mode=` (and may not support `respond_directly=`).
    We keep these parameters in the function signature so your CLI stays stable, but we do not pass
    them into Team().
    """
    leader_model = build_model(provider=leader_provider, model_id=leader_model_id)

    planning_agent = build_planning_agent(
        provider=planning_provider,
        model_id=planning_model_id,
        include_tools=planning_include_tools,
    )
    planning_agent.instructions = (planning_agent.instructions or "") + "\n\n" + DELEGATION_PREAMBLE

    execution_agent = build_execution_agent(
        provider=execution_provider,
        model_id=execution_model_id,
        include_tools=execution_include_tools,
    )
    execution_agent.instructions = (execution_agent.instructions or "") + "\n\n" + DELEGATION_PREAMBLE

    return Team(
        id="transit-team",
        name="Transit Orchestrator",
        model=leader_model,
        members=[planning_agent, execution_agent],
        instructions=dedent(TEAM_LEADER_INSTRUCTIONS).strip(),
        markdown=True,
        show_members_responses=False,
    )
