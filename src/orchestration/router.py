from __future__ import annotations

from textwrap import dedent
from typing import Iterable, Optional

from agno.team import Team

from .leader_tools import render_active_routes

from src.llm import build_model
from src.agents import build_execution_agent, build_planning_agent
from .policies import TEAM_LEADER_INSTRUCTIONS


DELEGATION_PREAMBLE = """\
You are being invoked by an orchestrator that already prepared the data for this user question.

Data consistency rule:
- Do NOT call fetch_static(...) or fetch_realtime() unless the orchestrator explicitly asks you to refresh data.
- Assume all tool calls for this question must operate on the SAME on-disk dataset/snapshot.

Grounding rule:
- Do not invent route names, stop names, or vehicle IDs. If data is missing, report it explicitly.
"""


def build_transit_team(
    *,
    mode: str = "coordinate",
    respond_directly: bool = False,
    leader_provider: str = "ollama",
    leader_model_id: str = "llama3.1:8b",
    planning_provider: str = "ollama",
    planning_model_id: str = "llama3.1:8b",
    execution_provider: str = "ollama",
    execution_model_id: str = "llama3.1:8b",
    planning_mcp_command: str,
    execution_mcp_command: str,
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
        mcp_command=planning_mcp_command,
        include_tools=planning_include_tools,
    )
    planning_agent.instructions = (planning_agent.instructions or "") + "\n\n" + DELEGATION_PREAMBLE

    execution_agent = build_execution_agent(
        provider=execution_provider,
        model_id=execution_model_id,
        mcp_command=execution_mcp_command,
        include_tools=execution_include_tools,
    )
    execution_agent.instructions = (execution_agent.instructions or "") + "\n\n" + DELEGATION_PREAMBLE

    team_kwargs = dict(
        id="transit-team",
        name="Transit Orchestrator",
        model=leader_model,
        members=[planning_agent, execution_agent],
        instructions=dedent(TEAM_LEADER_INSTRUCTIONS).strip(),
        markdown=True,
        show_members_responses=False,
    )

    # Leader-only formatter tool(s): keeps MCP tool outputs strictly machine-readable.
    try:
        import inspect
        if "tools" in inspect.signature(Team).parameters:
            team_kwargs["tools"] = [render_active_routes]
    except Exception:
        # If signature inspection fails, proceed without injecting tools.
        pass

    return Team(**team_kwargs)


# ---------------------------------------------------------------------------
# Backwards-compatible API
# ---------------------------------------------------------------------------

def build_team(**kwargs) -> Team:
    """Backwards-compatible alias.

    Older code paths import `build_team` from this module. The canonical
    implementation is `build_transit_team`.
    """
    return build_transit_team(**kwargs)
