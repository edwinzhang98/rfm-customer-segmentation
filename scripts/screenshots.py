"""Screenshot every page of the Streamlit app into docs/images/ (used by the README).

    python scripts/screenshots.py

Starts the app on a free port, opens each page in headless Chrome (Playwright, using the locally
installed Google Chrome - no browser download needed), waits for the charts, saves one PNG per page.
"""

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
PAGES = [
    ("", "1_overview"),  # the default page lives at "/"
    ("data-checks", "2_data_checks"),
    ("rfm-scoring", "3_rfm_scoring"),
    ("segments", "4_segments"),
    ("drill-down", "5_drill_down"),
    ("at-risk", "6_at_risk"),
    ("campaign", "7_campaign"),
    ("cohorts", "8_cohorts"),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(height: int = 1500) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard/app.py", "--server.port", str(port),
                             "--server.headless", "true"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/_stcore/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": height}, device_scale_factor=1)
            for path, name in PAGES:
                t0 = time.perf_counter()
                page.goto(f"{base}/{path}", wait_until="networkidle")
                page.wait_for_selector("h1", timeout=60_000)
                try:
                    page.wait_for_selector(".js-plotly-plot .main-svg", timeout=60_000)
                except Exception:
                    pass
                page.wait_for_timeout(2500)  # let every chart on the first screen finish drawing
                page.screenshot(path=str(OUT / f"dashboard_{name}.png"))
                print(f"  {name:<16} {time.perf_counter() - t0:5.1f} s")
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    main()
