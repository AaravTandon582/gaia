"""Capture real dashboard screenshots for the frontend README.

Run from the repository root. Requires the frontend on :3000 and backend on
:8000. Uses the system Google Chrome via Playwright.

Prereq: `pip install playwright` (browser deps auto-installed).
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = REPO / "frontend" / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

DASHBOARD_URL = "http://127.0.0.1:3000/dashboard"


async def take_ss(page, name, full_page=False):
    path = SCREENSHOTS_DIR / name
    await page.screenshot(path=path, full_page=full_page)
    print(f"saved {path} ({path.stat().st_size} bytes)")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            headless=True,
            args=["--window-size=1440,1024", "--hide-scrollbars", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1024}, device_scale_factor=1
        )
        page = await context.new_page()
        page.on("pageerror", lambda e: print(f"PAGE ERROR: {e}"))

        # 1. Main dashboard (before scan).
        print("1/5 loading dashboard ...")
        await page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        await take_ss(page, "dashboard-main.png", full_page=True)

        # 2. Select Amazon Basin region.
        print("2/5 selecting Amazon Basin ...")
        await page.get_by_role("button", name="Amazon Basin").first.click(timeout=10000)
        await page.wait_for_timeout(1000)

        # 3. Run the scan.
        print("3/5 running scan ...")
        await page.get_by_role("button", name="Run scan").first.click(timeout=10000)
        # Poll for scan completion (results panel appears).
        for _ in range(20):
            complete = await page.query_selector("text=statistical association")
            if complete:
                break
            await page.wait_for_timeout(1500)
        await page.wait_for_timeout(2000)

        print("4/5 capturing results panel ...")
        await take_ss(page, "results-panel.png", full_page=True)

        # Click a statistical association link for the detail view.
        print("5/5 capturing detail + anomaly bands ...")
        links = page.get_by_role("link")
        locator_list = await links.all()
        for l in locator_list:
            try:
                text = (await l.inner_text()).strip()
                if "→" in text and len(text) < 60:
                    await l.click(timeout=5000)
                    break
            except Exception:
                continue
        await page.wait_for_timeout(2000)
        await take_ss(page, "detail-panel.png", full_page=True)

        # Wait for anomaly bands to render (LSTM complete).
        for _ in range(15):
            if await page.query_selector("text=Combined-model anomaly"):
                break
            await page.wait_for_timeout(1500)
        await page.wait_for_timeout(2000)
        await take_ss(page, "anomaly-bands.png", full_page=True)

        await browser.close()
        print("done")


if __name__ == "__main__":
    asyncio.run(main())
