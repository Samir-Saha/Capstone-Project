"""End-to-end playthrough of all three modes in a real browser.

Test harness only: to answer boss questions correctly it reads the verified key
straight from the local SQLite file (REPS_DB_PATH). The app never sends keys to
the browser before an answer.

Usage (both servers running):
  REPS_DB_PATH=... python e2e/playthrough.py --out screenshots/
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("REPS_WEB_URL", "http://localhost:3000")
REFERENCE_WINDOW = '''def solve(minutes, budget):
    best = 0
    left = 0
    total = 0
    for right, m in enumerate(minutes):
        total += m
        while total > budget and left <= right:
            total -= minutes[left]
            left += 1
        best = max(best, right - left + 1)
    return best
'''


def key_for(question_text: str) -> str:
    db = sqlite3.connect(os.environ["REPS_DB_PATH"])
    row = db.execute("select answer from exam_questions order by created_at desc limit 1").fetchone()
    db.close()
    return row[0]


def shot(page: Page, out: Path, name: str, full: bool = False) -> None:
    page.wait_for_timeout(400)
    page.screenshot(path=str(out / f"{name}.png"), full_page=full)
    print("  screenshot", name)


def boss_fight(page: Page, out: Path) -> None:
    print("boss fight")
    page.goto(f"{BASE}/exam")
    expect(page.get_by_role("heading", name="Vexis, the Limitless")).to_be_visible(timeout=20000)
    shot(page, out, "02-bosses", full=True)
    page.get_by_role("button", name="Start the fight").first.click()
    page.wait_for_url("**/exam/*", timeout=20000)
    expect(page.get_by_text("Key verified")).to_be_visible(timeout=30000)
    shot(page, out, "03-fight-question")

    for i in range(4):
        expect(page.get_by_label("Your answer")).to_be_enabled(timeout=30000)
        answer = key_for("") if i != 2 else "424242"
        page.get_by_label("Your answer").fill(answer)
        page.wait_for_timeout(500)  # live preview
        if i == 0:
            shot(page, out, "04-fight-typed")
        page.keyboard.press("Enter")
        verdict = "Direct hit" if i != 2 else "Blocked"
        expect(page.get_by_text(verdict, exact=True)).to_be_visible(timeout=20000)
        if i in (0, 2):
            shot(page, out, f"05-fight-{'hit' if i == 0 else 'blocked'}")
        page.get_by_role("button", name="Next attack").click()
    expect(page.get_by_text("Key verified")).to_be_visible(timeout=30000)
    page.get_by_role("button", name="Retreat").click()
    page.get_by_role("button", name="Retreat").last.click()
    page.wait_for_url("**/results", timeout=20000)
    expect(page.get_by_text("Mastery by topic")).to_be_visible(timeout=20000)
    shot(page, out, "06-fight-results", full=True)


def arena(page: Page, out: Path) -> None:
    print("arena")
    page.goto(f"{BASE}/arena")
    expect(page.get_by_text("Longest Study Streak on a Budget")).to_be_visible(timeout=30000)
    shot(page, out, "07-arena")
    page.get_by_text("Longest Study Streak on a Budget").click()
    expect(page.get_by_role("heading", name="Longest Study Streak on a Budget")).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Run").click()
    expect(page.get_by_text("Wrong answer")).to_be_visible(timeout=20000)
    shot(page, out, "08-arena-run-wrong")
    editor = page.locator(".cm-content")
    editor.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    # CodeMirror auto-indents; insert the text without typing keystrokes.
    page.keyboard.insert_text(REFERENCE_WINDOW)
    page.get_by_role("button", name="Submit").click()
    expect(page.get_by_text("Accepted", exact=True)).to_be_visible(timeout=30000)
    shot(page, out, "09-arena-accepted")


def interview(page: Page, out: Path) -> None:
    print("interview")
    page.goto(f"{BASE}/interview")
    expect(page.get_by_role("heading", name="Gauntlet")).to_be_visible(timeout=20000)
    shot(page, out, "10-interview-setup", full=True)
    page.get_by_text("Quant and trading").click()
    page.get_by_role("button", name="Enter the room").click()
    page.wait_for_url("**/interview/*", timeout=20000)
    expect(page.get_by_text("Your answer", exact=True)).to_be_visible(timeout=20000)
    answers = [
        "We worked on a group project and we finished it together and our professor liked it.",
        "I led the club's budget review. I tracked every expense in a sheet, compared it to last year, and cut spending by 18 percent.",
        "I chose the simpler model because I measured both on held-out data and the gap was under 1 percent, which meant faster iteration.",
        "I organized volunteers across five states, which resulted in 70 people joining.",
        "I rebuilt the schedule and it saved about 6 hours a week.",
        "I owned the analysis and I presented it.",
    ]
    for n in range(8):
        if page.get_by_role("button", name="Finish and see the report").is_visible():
            break
        page.get_by_role("tab", name="Type").click()
        page.get_by_label("Type your answer").fill(answers[n % len(answers)])
        if n == 0:
            shot(page, out, "11-interview-room")
        page.get_by_role("button", name="Submit answer").click()
        page.wait_for_timeout(700)
        if n == 0:
            shot(page, out, "12-interview-followup")
    page.get_by_role("button", name="Finish and see the report").click()
    page.wait_for_url("**/report", timeout=30000)
    expect(page.get_by_role("heading", name="Interview report")).to_be_visible(timeout=20000)
    shot(page, out, "13-interview-report", full=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="screenshots")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": args.width, "height": args.height})
        page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(BASE)
        expect(page.get_by_text("Boss fights").first).to_be_visible(timeout=20000)
        shot(page, out, "01-hub-new", full=True)
        if page.get_by_placeholder("What should Reps call you?").is_visible():
            page.get_by_placeholder("What should Reps call you?").fill("Samir")
            page.get_by_role("button", name="Save").click()
            expect(page.get_by_role("heading", level=1)).to_contain_text("Samir")
        boss_fight(page, out)
        arena(page, out)
        interview(page, out)
        page.goto(BASE)
        expect(page.get_by_role("heading", name="Weak spots")).to_be_visible(timeout=20000)
        time.sleep(1)
        shot(page, out, "14-hub-after", full=True)
        browser.close()
    if errors:
        print("\nBrowser errors:")
        for e in errors:
            print(" ", e)
    return 1 if any("pageerror" in e for e in errors) else 0


if __name__ == "__main__":
    sys.exit(main())
