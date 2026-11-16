"""Capture the discovery summary table screenshot."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "frontend" / "docs" / "screenshots"

DASHBOARD_URL = "http://127.0.0.1:3000/dashboard"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
            args=["--window-size=1440,1024", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1024}, device_scale_factor=1
        )
        page = await context.new_page()

        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        await page.get_by_role("button", name="Amazon Basin").first.click(timeout=10000)
        await page.get_by_role("button", name="Run scan").first.click(timeout=10000)
        for _ in range(20):
            if await page.query_selector("text=statistical association"):
                break
            await page.wait_for_timeout(1500)
        await page.wait_for_timeout(2000)

        # Scroll to the discovery summary table and capture it.
        await page.get_by_text("Discovery summary", exact=True).first.scroll_into_view_if_needed()
        await page.wait_for_timeout(1000)
        summary = page.locator("section[aria-label='Discovery statistics']")
        await summary.screenshot(path=OUT / "summary-table.png")
        print(f"saved {OUT / 'summary-table.png'}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
