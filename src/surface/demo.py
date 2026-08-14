from __future__ import annotations

import argparse
import asyncio

from src.surface.browser import BrowserSurface


async def run(target: str, member_id: str, headless: bool) -> None:
    async with BrowserSurface(headless=headless) as surface:
        await surface.navigate(target)

        before = await surface.observe()
        print(f"Opened: {before.title} ({before.url})")

        await surface.type('input[name="member_id"]', member_id)
        await surface.click('button[type="submit"]')

        after = await surface.observe()
        print("--- Current page ---")
        print(after.body_text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drive the Stage 2 mock bank through ComputerSurface."
    )
    parser.add_argument(
        "--target",
        default="http://127.0.0.1:8000",
        help="Mock-bank entry point.",
    )
    parser.add_argument("--member-id", default="12345")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the Chromium window.",
    )
    args = parser.parse_args()

    asyncio.run(
        run(
            target=args.target,
            member_id=args.member_id,
            headless=not args.headed,
        )
    )


if __name__ == "__main__":
    main()
