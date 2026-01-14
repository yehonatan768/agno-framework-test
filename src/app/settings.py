from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(key)
    if v is None or v == "":
        return default
    return v


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppSettings:
    """
    Centralized runtime settings for the app.

    Intended behavior:
    - Loads .env (if present) and then reads environment variables.
    - Provides sane defaults so local dev works immediately.

    Environment variables:
      OPENAI_API_KEY                 (required by OpenAI provider)
      OPENAI_MODEL                   default model id for all agents (e.g., gpt-4o-mini)
      LEADER_MODEL                   override for orchestration leader
      PLANNING_MCP_COMMAND           stdio command for planning MCP server
      EXECUTION_MCP_COMMAND          stdio command for execution MCP server
      TEAM_MODE                      route|coordinate|collaborate
      TEAM_RESPOND_DIRECTLY          true/false
      SHOW_TOOL_CALLS                true/false
    """
    openai_model: str
    leader_model: str
    planning_mcp_command: str
    execution_mcp_command: str

    team_mode: str
    team_respond_directly: bool
    show_tool_calls: bool

    @classmethod
    def load(cls, dotenv_path: str | Path = ".env") -> "AppSettings":
        load_dotenv(dotenv_path=str(dotenv_path), override=False)

        openai_model = _env("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        leader_model = _env("LEADER_MODEL", openai_model) or openai_model

        planning_cmd = _env("PLANNING_MCP_COMMAND", "python -m src.mcp_servers.planning.server") or                        "python -m src.mcp_servers.planning.server"
        execution_cmd = _env("EXECUTION_MCP_COMMAND", "python -m src.mcp_servers.execution.server") or                         "python -m src.mcp_servers.execution.server"

        team_mode = _env("TEAM_MODE", "coordinate") or "coordinate"
        team_respond_directly = _env_bool("TEAM_RESPOND_DIRECTLY", False)
        show_tool_calls = _env_bool("SHOW_TOOL_CALLS", True)

        return cls(
            openai_model=openai_model,
            leader_model=leader_model,
            planning_mcp_command=planning_cmd,
            execution_mcp_command=execution_cmd,
            team_mode=team_mode,
            team_respond_directly=team_respond_directly,
            show_tool_calls=show_tool_calls,
        )
