from __future__ import annotations

import asyncio

from src.orchestration import build_transit_team


async def main() -> None:
    team = build_transit_team(mode="coordinate")
    # Example prompt:
    await team.aprint_response("List the agencies in the static GTFS and then load the latest snapshot and tell me how many vehicles are present.", stream=True)


if __name__ == "__main__":
    asyncio.run(main())
