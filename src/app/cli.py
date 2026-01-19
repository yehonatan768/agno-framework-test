from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from src.agents import build_execution_agent, build_planning_agent
from src.orchestration.router import build_transit_team
from src.sources.gtfs_static.fetch import main as fetch_static_main
from src.sources.gtfs_realtime.fetch import main as fetch_realtime_main

from .settings import AppSettings


def _add_common_prompt_args(p: argparse.ArgumentParser) -> None:
    # Support both --prompt and --question as synonyms.
    # The product-style command is --question; --prompt is kept for compatibility.
    p.add_argument(
        "--question",
        "--prompt",
        "-p",
        type=str,
        default=None,
        help="Question/prompt to run once. If omitted, reads from stdin.",
    )
    p.add_argument("--stream", action="store_true", help="Stream output tokens (if supported).")


def _read_prompt(prompt_or_question: Optional[str]) -> str:
    if prompt_or_question and prompt_or_question.strip():
        return prompt_or_question.strip()
    data = sys.stdin.read()
    if not data.strip():
        raise SystemExit("No question provided. Use --question/--prompt or pipe text into stdin.")
    return data.strip()


async def _run_fetch_static(_: argparse.Namespace, __: AppSettings) -> None:
    rc = fetch_static_main()
    if rc != 0:
        raise SystemExit(rc)


async def _run_fetch_realtime(_: argparse.Namespace, __: AppSettings) -> None:
    rc = fetch_realtime_main()
    if rc != 0:
        raise SystemExit(rc)


async def _run_planning(args: argparse.Namespace, s: AppSettings) -> None:
    agent = build_planning_agent(
        provider=s.planning_llm_provider,
        model_id=s.planning_llm_model,
        mcp_command=s.planning_mcp_command,
        show_tool_calls=s.show_tool_calls,
    )
    prompt = _read_prompt(args.question)
    await agent.aprint_response(prompt, stream=args.stream)


async def _run_execution(args: argparse.Namespace, s: AppSettings) -> None:
    agent = build_execution_agent(
        provider=s.execution_llm_provider,
        model_id=s.execution_llm_model,
        mcp_command=s.execution_mcp_command,
        show_tool_calls=s.show_tool_calls,
    )
    prompt = _read_prompt(args.question)
    await agent.aprint_response(prompt, stream=args.stream)


async def _run_team(args: argparse.Namespace, s: AppSettings) -> None:
    team = build_transit_team(
        mode=args.mode or s.team_mode,
        respond_directly=args.respond_directly if args.respond_directly is not None else s.team_respond_directly,
        leader_provider=s.leader_llm_provider,
        leader_model_id=s.leader_llm_model,
        planning_provider=s.planning_llm_provider,
        planning_model_id=s.planning_llm_model,
        execution_provider=s.execution_llm_provider,
        execution_model_id=s.execution_llm_model,
        planning_mcp_command=s.planning_mcp_command,
        execution_mcp_command=s.execution_mcp_command,
    )
    prompt = _read_prompt(args.question)
    await team.aprint_response(prompt, stream=args.stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transit-app",
        description="Transit MCP + Agno app CLI (Planning Agent, Execution Agent, Orchestrator Team).",
    )

    parser.add_argument("--dotenv", type=str, default=".env", help="Path to .env file (default: .env)")

    # Product-style single-command mode:
    #   py -m src.cli --question "..."
    # If no subcommand is provided, we route the question through the orchestrator (team).
    _add_common_prompt_args(parser)
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        choices=["route", "coordinate", "collaborate"],
        help="(No-subcommand mode only) Override team mode (route|coordinate|collaborate).",
    )
    parser.add_argument(
        "--respond-directly",
        dest="respond_directly",
        action="store_true",
        help="(No-subcommand mode only) Selected member responds directly without leader synthesis.",
    )
    parser.add_argument(
        "--no-respond-directly",
        dest="respond_directly",
        action="store_false",
        help="(No-subcommand mode only) Force leader synthesis.",
    )
    parser.set_defaults(respond_directly=None)

    # Keep developer/test subcommands, but do not require them.
    sub = parser.add_subparsers(dest="cmd", required=False)

    p_plan = sub.add_parser("planning", help="Run the Planning Agent (static GTFS only).")
    _add_common_prompt_args(p_plan)

    p_exec = sub.add_parser("execution", help="Run the Execution Agent (realtime GTFS-RT only).")
    _add_common_prompt_args(p_exec)

    p_fs = sub.add_parser("fetch-static", help="Download + extract the static GTFS feed to dataset/static.")
    p_fs.add_argument("--stream", action="store_true", help="No-op (kept for symmetry).")

    p_fr = sub.add_parser("fetch-realtime", help="Download realtime GTFS-RT feeds into dataset/realtime/<ts>/")
    p_fr.add_argument("--stream", action="store_true", help="No-op (kept for symmetry).")

    p_team = sub.add_parser("team", help="Run the Orchestrator (Team) that coordinates both agents.")
    _add_common_prompt_args(p_team)
    p_team.add_argument(
        "--mode",
        type=str,
        default=None,
        choices=["route", "coordinate", "collaborate"],
        help="Override team mode (route|coordinate|collaborate). Defaults to TEAM_MODE.",
    )
    p_team.add_argument(
        "--respond-directly",
        dest="respond_directly",
        action="store_true",
        help="If set, a selected member responds directly without leader synthesis.",
    )
    p_team.add_argument(
        "--no-respond-directly",
        dest="respond_directly",
        action="store_false",
        help="Force leader synthesis (default).",
    )
    p_team.set_defaults(respond_directly=None)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = AppSettings.load(args.dotenv)

    # If no subcommand was given, treat this as the user-facing "ask" mode.
    # Route the question through the orchestrator/team.
    if args.cmd is None:
        asyncio.run(_run_team(args, settings))
        return

    if args.cmd == "fetch-static":
        asyncio.run(_run_fetch_static(args, settings))
    elif args.cmd == "fetch-realtime":
        asyncio.run(_run_fetch_realtime(args, settings))
    elif args.cmd == "planning":
        asyncio.run(_run_planning(args, settings))
    elif args.cmd == "execution":
        asyncio.run(_run_execution(args, settings))
    elif args.cmd == "team":
        asyncio.run(_run_team(args, settings))
    else:
        raise SystemExit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
