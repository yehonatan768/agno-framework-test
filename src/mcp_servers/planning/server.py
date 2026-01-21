from __future__ import annotations

"""Planning MCP server (static-only).

Exposes static GTFS tools: dataset introspection, mappings, integrity checks.
Run (stdio transport):
  python -m src.mcp_servers.planning.server
"""

from mcp.server.fastmcp import FastMCP

from . import tools


mcp = FastMCP("TransitPlanning", json_response=True)


@mcp.tool()
def list_static_tables() -> dict:
    return tools.list_static_tables().model_dump()


@mcp.tool()
def describe_table(table: str, max_unique: int = 20, sample_rows: int = 5) -> dict:
    return tools.describe_table(table, max_unique=max_unique, sample_rows=sample_rows).model_dump()


@mcp.tool()
def list_agencies() -> dict:
    return tools.list_agencies().model_dump()


@mcp.tool()
def export_routes() -> dict:
    return tools.export_routes().model_dump()


@mcp.tool()
def export_stops() -> dict:
    return tools.export_stops().model_dump()


@mcp.tool()
def stops_bbox() -> dict:
    return tools.stops_bbox().model_dump()


@mcp.tool()
def route_trip_counts(top_n: int | None = None) -> dict:
    return tools.route_trip_counts(top_n=top_n).model_dump()


@mcp.tool()
def trip_stop_sequence(trip_id: str) -> dict:
    return tools.trip_stop_sequence(trip_id).model_dump()


@mcp.tool()
def route_stops(route_id: str) -> dict:
    return tools.route_stops(route_id).model_dump()


@mcp.tool()
def stop_routes(stop_id: str) -> dict:
    return tools.stop_routes(stop_id).model_dump()


@mcp.tool()
def integrity_report() -> dict:
    return tools.integrity_report().model_dump()


@mcp.tool()
def data_quality_report() -> dict:
    return tools.data_quality_report().model_dump()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
