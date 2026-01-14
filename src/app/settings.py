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
    # Base LLM (default for everything unless overridden)
    llm_provider: str
    llm_model: str

    # Per-role overrides
    leader_llm_provider: str
    leader_llm_model: str
    planning_llm_provider: str
    planning_llm_model: str
    execution_llm_provider: str
    execution_llm_model: str

    # MCP commands
    planning_mcp_command: str
    execution_mcp_command: str

    # Team behavior
    team_mode: str
    team_respond_directly: bool
    show_tool_calls: bool

    @classmethod
    def load(cls, dotenv_path: str | Path = ".env") -> "AppSettings":
        load_dotenv(dotenv_path=str(dotenv_path), override=False)

        base_provider = (_env("LLM_PROVIDER", "openai") or "openai").strip()
        base_model = (_env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini").strip()

        leader_provider = (_env("LEADER_LLM_PROVIDER", base_provider) or base_provider).strip()
        leader_model = (_env("LEADER_LLM_MODEL", base_model) or base_model).strip()

        planning_provider = (_env("PLANNING_LLM_PROVIDER", base_provider) or base_provider).strip()
        planning_model = (_env("PLANNING_LLM_MODEL", base_model) or base_model).strip()

        execution_provider = (_env("EXECUTION_LLM_PROVIDER", base_provider) or base_provider).strip()
        execution_model = (_env("EXECUTION_LLM_MODEL", base_model) or base_model).strip()

        planning_cmd = _env("PLANNING_MCP_COMMAND", "python -m src.mcp_servers.planning.server") or \
                       "python -m src.mcp_servers.planning.server"
        execution_cmd = _env("EXECUTION_MCP_COMMAND", "python -m src.mcp_servers.execution.server") or \
                        "python -m src.mcp_servers.execution.server"

        team_mode = (_env("TEAM_MODE", "coordinate") or "coordinate").strip()
        team_respond_directly = _env_bool("TEAM_RESPOND_DIRECTLY", False)
        show_tool_calls = _env_bool("SHOW_TOOL_CALLS", True)

        return cls(
            llm_provider=base_provider,
            llm_model=base_model,
            leader_llm_provider=leader_provider,
            leader_llm_model=leader_model,
            planning_llm_provider=planning_provider,
            planning_llm_model=planning_model,
            execution_llm_provider=execution_provider,
            execution_llm_model=execution_model,
            planning_mcp_command=planning_cmd,
            execution_mcp_command=execution_cmd,
            team_mode=team_mode,
            team_respond_directly=team_respond_directly,
            show_tool_calls=show_tool_calls,
        )
