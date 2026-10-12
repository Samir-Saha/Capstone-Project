"""Party raid playthrough: two players in two browsers (desktop host, phone guest).

The API runs inside this process so the test can read each player's answer key from
the room; the browsers never see keys. Stop your own API first (this uses port 8000),
start the web app (`npm run build && npm start`), then:

  python e2e/party.py [--out screenshots/]
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("REPS_DB_PATH", str(Path(tempfile.mkdtemp(prefix="reps-party-")) / "reps.db"))
os.environ["REPS_SKIP_WARMUP"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
import uvicorn  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from reps_api import party  # noqa: E402
from reps_api.main import app  # noqa: E402



OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else tempfile.mkdtemp(prefix="reps-party-shots-")
BASE = "http://localhost:3000"
errors = []


def main():
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.1)
    

    def key_for(code, name):
        for _ in range(300):
            room = party.HUB.rooms[code]
            p = next(p for p in room.players.values() if p.name == name)
            if p.question and not p.busy:
                return p.question.answer
            time.sleep(0.05)
        raise RuntimeError("no question")

    def strike(page, text):
        page.get_by_label("Your answer").fill(text)
        page.keyboard.press("Enter")

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        host = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        guest = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
        for pg in (host, guest):
            pg.on("pageerror", lambda e: errors.append(str(e)))

        host.goto(f"{BASE}/party")
        host.get_by_label("Your name in the raid").fill("Samir")
        host.get_by_role("radio").first.wait_for()
        host.screenshot(path=f"{OUT}/p1-party-home.png", full_page=True)
        host.get_by_role("button", name="Open a room").click()
        host.wait_for_url("**/party/*")
        code = host.url.rstrip("/").split("/")[-1]
        expect(host.get_by_text("Room code")).to_be_visible()

        guest.goto(f"{BASE}/party")
        guest.get_by_label("Your name in the raid").fill("Meg")
        guest.get_by_label("Room code").fill(code.lower())
        guest.get_by_role("button", name="Join", exact=True).click()
        guest.wait_for_url(f"**/party/{code}")
        expect(host.get_by_text("Meg")).to_be_visible()
        host.wait_for_timeout(400)
        host.screenshot(path=f"{OUT}/p2-lobby-host.png")
        guest.screenshot(path=f"{OUT}/p3-lobby-guest.png", full_page=True)
        host.get_by_role("button", name="Start the raid").click()
        expect(host.get_by_text("Key verified")).to_be_visible(timeout=30000)
        expect(guest.get_by_text("Key verified")).to_be_visible(timeout=30000)
        # host hits twice, guest misses once then hits
        strike(host, key_for(code, "Samir"))
        expect(host.get_by_text("Direct hit")).to_be_visible(timeout=15000)
        host.wait_for_timeout(300)
        host.screenshot(path=f"{OUT}/p4-host-hit.png")
        strike(guest, "424242")
        expect(guest.get_by_text("Blocked")).to_be_visible(timeout=15000)
        guest.screenshot(path=f"{OUT}/p5-guest-miss.png")
        host.get_by_role("button", name="Next question").click()
        strike(host, key_for(code, "Samir"))
        expect(host.get_by_text("Direct hit")).to_be_visible(timeout=15000)
        host.get_by_role("button", name="Next question").click()
        guest.get_by_role("button", name="Next question").click()
        strike(guest, key_for(code, "Meg"))
        expect(guest.get_by_text("Direct hit")).to_be_visible(timeout=15000)
        guest.get_by_role("button", name="Next question").click()
        expect(host.get_by_text("Meg hit for")).to_be_visible(timeout=10000)
        host.wait_for_timeout(500)
        host.screenshot(path=f"{OUT}/p6-host-active.png", full_page=True)
        guest.screenshot(path=f"{OUT}/p7-guest-active.png", full_page=True)
        # finish: knock the boss down to a sliver and land the last hit
        room = party.HUB.rooms[code]
        room.hp = 5
        strike(host, key_for(code, "Samir"))
        expect(host.get_by_text("Direct hit")).to_be_visible(timeout=15000)
        host.get_by_role("button", name="See the result").click()
        expect(host.get_by_text("Boss down")).to_be_visible(timeout=10000)
        expect(guest.get_by_text("Boss down")).to_be_visible(timeout=10000)
        host.wait_for_timeout(900)
        host.screenshot(path=f"{OUT}/p8-victory.png", full_page=True)
        print("scrollWidth guest", guest.evaluate("document.documentElement.scrollWidth"))
        host.get_by_role("button", name="Run it back").click()
        expect(guest.get_by_text("Waiting for Samir to start.")).to_be_visible(timeout=10000)
        print("run it back ok")
        b.close()
    print("page errors:", errors or "none")
    print("screenshots in", OUT)
    if errors:
        sys.exit(1)
    server.should_exit = True


if __name__ == '__main__':
    main()
