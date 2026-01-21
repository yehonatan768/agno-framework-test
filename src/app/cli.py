from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Optional

from .settings import AppSettings
from ..orchestration.router import build_team


@dataclass(frozen=True)
class CliArgs:
    question: str
    show_tool_calls: bool
    respond_directly: bool


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="src.cli", description="Transit multi-agent CLI (Planning + Execution via MCP).")
    p.add_argument(
        "--question",
        "-q",
        required=True,
        help="User question to ask the team.",
    )
    p.add_argument(
        "--show-tool-calls",
        action="store_true",
        help="Show tool calls and intermediate agent activity (debug).",
    )
    p.add_argument(
        "--respond-directly",
        action="store_true",
        help="Ask the leader to answer directly (avoid verbose internal reasoning).",
    )
    return p


def _parse_args(argv: list[str]) -> CliArgs:
    ns = _build_parser().parse_args(argv)
    return CliArgs(
        question=str(ns.question),
        show_tool_calls=bool(ns.show_tool_calls),
        respond_directly=bool(ns.respond_directly),
    )


def run(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parse_args(argv)

    settings = AppSettings.load()

    team = build_team(
        settings=settings,
        show_tool_calls=args.show_tool_calls,
        respond_directly=args.respond_directly,
    )

    result = team.run(args.question)

    # Agno typically returns either a string, or an object with `.content`.
    if isinstance(result, str):
        print(result)
    else:
        content = getattr(result, "content", None)
        print(content if content is not None else str(result))

    return 0


def main() -> None:
    raise SystemExit(run())
