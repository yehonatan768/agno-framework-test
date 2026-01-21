from __future__ import annotations

"""Execution MCP server.

Exposes realtime-heavy tools (snapshot loading, joins, proximity queries).
Run (stdio transport):
  python -m src.mcp_servers.execution.server
"""

from mcp.server.fastmcp import FastMCP

from . import tools


mcp = FastMCP("TransitExecution", json_response=True)


@mcp.tool()
def snapshot_stats() -> dict:
    return tools.snapshot_stats().model_dump()


@mcp.tool()
def load_latest_snapshot() -> dict:
    return tools.load_latest_snapshot().model_dump()


@mcp.tool()
def load_snapshot_dir(snapshot_dir: str) -> dict:
    return tools.load_snapshot_dir(snapshot_dir).model_dump()


@mcp.tool()
def load_static_tables() -> dict:
    return tools.load_static_tables().model_dump()


@mcp.tool()
def get_vehicle_position(vehicle_id: str) -> dict:
    return tools.get_vehicle_position(vehicle_id).model_dump()


@mcp.tool()
def vehicles_on_route(route_id: str) -> dict:
    return tools.vehicles_on_route(route_id).model_dump()


@mcp.tool()
def vehicles_near_vehicle(vehicle_id: str, radius_m: float, limit: int = 50) -> dict:
    return tools.vehicles_near_vehicle(vehicle_id, radius_m, limit=limit).model_dump()


@mcp.tool()
def build_enriched_vehicle_view() -> dict:
    return tools.build_enriched_vehicle_view().model_dump()


@mcp.tool()
def active_routes_with_vehicles() -> dict:
    """List routes that currently have active vehicles (from latest snapshot) enriched with route names."""
    return tools.active_routes_with_vehicles().model_dump()


@mcp.tool()
def fetch_realtime() -> dict:
    return tools.fetch_realtime().model_dump()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
