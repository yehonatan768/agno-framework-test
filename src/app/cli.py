from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Optional

from src.agents import build_execution_agent, build_planning_agent
from src.orchestration.router import build_transit_team
from src.sources.fetch import fetch_all

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
    """Run the orchestrator.

    Important implementation detail:
    - Many local models/providers (e.g., Ollama) do not reliably support tool/function calling for the Team leader.
      In those cases the leader can emit a "delegate_task_to_member" tool call but never produce a final synthesis.
    - Your version of Agno's Team API also does not support "respond_directly" routing.

    To make the CLI robust, we implement a deterministic, code-level router when:
      - --respond-directly is set (or TEAM_RESPOND_DIRECTLY=true), OR
      - team mode is 'route'.
    """

    prompt = _read_prompt(args.question)
    mode = (args.mode or s.team_mode or "coordinate").strip().lower()
    respond_directly = args.respond_directly if args.respond_directly is not None else s.team_respond_directly

    def _classify(q: str) -> str:
        ql = q.lower()
        # Strong realtime indicators
        realtime_terms = [
            "realtime",
            "real-time",
            "right now",
            "currently",
            "active vehicles",
            "vehicle",
            "vehicles",
            "delay",
            "delayed",
            "alert",
            "near",
            "nearest",
            "position",
            "where is",
            "location",
        ]
        static_terms = [
            "schedule",
            "timetable",
            "calendar",
            "stop",
            "stops",
            "station",
            "route map",
            "shape",
            "agency",
        ]
        if any(t in ql for t in realtime_terms) and any(t in ql for t in static_terms):
            return "both"
        if any(t in ql for t in realtime_terms):
            return "execution"
        if any(t in ql for t in static_terms):
            return "planning"
        # default: coordinate via leader
        return "team"

    if respond_directly or mode == "route":
        which = _classify(prompt)
        if which == "planning":
            await _run_planning(args, s)
            return
        if which == "execution":
            await _run_execution(args, s)
            return
        if which == "both":
            # Sequential (simple + deterministic). If you want parallel, we can add asyncio.gather.
            print("\n=== Planning Agent (static) ===\n")
            await _run_planning(args, s)
            print("\n=== Execution Agent (realtime) ===\n")
            await _run_execution(args, s)
            return

    # Default: use the Team leader synthesis.
    team = build_transit_team(
        mode=mode,
        respond_directly=respond_directly,
        leader_provider=s.leader_llm_provider,
        leader_model_id=s.leader_llm_model,
        planning_provider=s.planning_llm_provider,
        planning_model_id=s.planning_llm_model,
        execution_provider=s.execution_llm_provider,
        execution_model_id=s.execution_llm_model,
        planning_mcp_command=s.planning_mcp_command,
        execution_mcp_command=s.execution_mcp_command,
    )
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

    fetch_all()
    # If no subcommand was given, treat this as the user-facing "ask" mode.
    # Route the question through the orchestrator/team.
    if args.cmd is None:
        asyncio.run(_run_team(args, settings))
        return

    elif args.cmd == "execution":
        asyncio.run(_run_execution(args, settings))
    elif args.cmd == "team":
        asyncio.run(_run_team(args, settings))
    else:
        raise SystemExit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
