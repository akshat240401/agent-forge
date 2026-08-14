from __future__ import annotations

import argparse
import asyncio
import json

from src.surface.browser import BrowserSurface
from src.surface.observation import BrowserObserver


async def run(target: str, headed: bool) -> None:
    observer = BrowserObserver()

    async with BrowserSurface(headless=not headed) as surface:
        await surface.navigate(target)
        observation = await observer.observe(surface)
        print(json.dumps(observation.model_dump(mode="json"), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print AgentForge's structured UI observation."
    )
    parser.add_argument(
        "--target",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    asyncio.run(run(args.target, args.headed))


if __name__ == "__main__":
    main()
