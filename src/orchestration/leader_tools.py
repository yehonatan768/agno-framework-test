from __future__ import annotations

from typing import Any, Dict, List


def render_active_routes(payload: Dict[str, Any]) -> str:
    """Render ActiveRoutesOutput (tool output) into a concise, user-facing markdown answer.

    This is intentionally *leader-only* formatting logic. MCP tools must return raw data only.

    Expected payload shape (ActiveRoutesOutput):
      - snapshot_id: str
      - feed_timestamp: Optional[str]
      - routes: List[{
            route_id: str,
            route_short_name: Optional[str],
            route_long_name: Optional[str],
            vehicle_count: int,
            vehicles: List[{
                vehicle_id: str,
                vehicle_label: Optional[str],
                latitude: Optional[float],
                longitude: Optional[float],
                bearing: Optional[float],
                speed: Optional[float],
                timestamp: Optional[str],
            }]
        }]
    """

    snapshot_id = payload.get("snapshot_id") or "(unknown)"
    feed_ts = payload.get("feed_timestamp")
    routes: List[Dict[str, Any]] = payload.get("routes") or []

    if not routes:
        suffix = f" (snapshot {snapshot_id})"
        if feed_ts:
            suffix += f", feed timestamp {feed_ts}"
        return f"No active routes with vehicles were found{suffix}."

    header = f"Active routes with vehicles (snapshot {snapshot_id}"
    if feed_ts:
        header += f", feed timestamp {feed_ts}"
    header += "):"

    lines: List[str] = [header]
    for r in routes:
        rid = r.get("route_id", "?")
        rshort = r.get("route_short_name")
        rlong = r.get("route_long_name")
        vcount = int(r.get("vehicle_count") or 0)

        name_parts = []
        if rshort:
            name_parts.append(str(rshort))
        if rlong:
            name_parts.append(str(rlong))
        name = " — ".join(name_parts)

        if name:
            lines.append(f"- **{rid}** ({name}): {vcount} vehicle(s)")
        else:
            lines.append(f"- **{rid}**: {vcount} vehicle(s)")

        vehicles = r.get("vehicles") or []
        if vehicles:
            shown = []
            for v in vehicles[:8]:
                vid = v.get("vehicle_id") or v.get("id") or "?"
                vlabel = v.get("vehicle_label")
                shown.append(f"{vid}{f' ({vlabel})' if vlabel else ''}")
            more = "" if len(vehicles) <= 8 else f" (+{len(vehicles)-8} more)"
            lines.append(f"  - Vehicles: {', '.join(shown)}{more}")

    return "\n".join(lines)
