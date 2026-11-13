"""Browser tour of the chat inside a case (docs/case-management/13-plain-case-design.md, section 12), with fictional people.

    A case is set up (through the API, to keep the tour short): the Supervisor registers it, SI Arun leads it, SI Meena (Sub Investigator) and
    Dev (Analyst) are on the team. Then, on the screens, in separate browser windows:
    1. Arun writes to the whole team; Meena's Chat tab shows one unread message and she sees it, and answers.
    2. Meena writes privately to Dev; Dev sees it (and a notice); Arun does not see it anywhere, and neither does the Supervisor.
    3. The Supervisor, who oversees the case but is not on the team, has no Chat tab.

Same set-up as walkthrough.py (a throwaway database made by `python -m scripts.e2e_prepare`, API and web app running):
    uv run --with playwright==1.64.1 python ../frontend/e2e/chat_tour.py --url http://127.0.0.1:5180 --shots <folder>

All names are FICTIONAL. Exit code 0 only if every step passed.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import Browser, expect, sync_playwright

import walkthrough as w  # the helpers: Walk, PASSWORD

TITLE = "Chat tour case (FICTIONAL)"


def api(base: str, method: str, path: str, token: str | None = None, body=None, form=None):
    data = json.dumps(body).encode() if body is not None else (urllib.parse.urlencode(form).encode() if form else None)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(base + path, method=method, data=data, headers=headers), timeout=60) as response:
        return json.load(response)


def token_of(base: str, username: str) -> str:
    return api(base, "POST", "/api/auth/token", form={"username": username, "password": w.PASSWORD})["access_token"]


def run(walk: w.Walk, args: argparse.Namespace) -> None:
    url = walk.url
    ids = {name: api(url, "GET", "/api/auth/me", token_of(url, f"kh.{name}"))["id"] for name in ("supervisor", "arun", "meena", "dev")}
    sup_token, arun_token = token_of(url, "kh.supervisor"), token_of(url, "kh.arun")
    case = api(url, "POST", "/api/v1/cases", sup_token, {
        "title": TITLE, "case_type": "cyber_fraud", "lead_investigator_id": ids["arun"], "supervisor_id": ids["supervisor"],
        "description": "FICTIONAL: a complainant reports three unauthorised transfers after a fake KYC message."})
    for name, role in (("meena", "sub_investigator"), ("dev", "analyst")):
        api(url, "POST", f"/api/v1/cases/{case['case_id']}/team", arun_token, {"user_id": ids[name], "role": role})
    chat = f"{url}/kh/case/{case['case_id']}/chat"

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch()
        arun = walk.login(browser, "kh.arun")
        meena = walk.login(browser, "kh.meena")
        dev = walk.login(browser, "kh.dev")
        sup = walk.login(browser, "kh.supervisor")

        # ---------------------------------------------------------------- 1. a message to the whole team
        arun.goto(chat)
        expect(arun.get_by_text("Conversations", exact=True)).to_be_visible()
        arun.get_by_role("textbox", name="Message").fill("Meet at the station at nine to go over the CDR (fictional).")
        arun.get_by_role("textbox", name="Message").press("Enter")
        expect(arun.get_by_text("Meet at the station at nine to go over the CDR (fictional).")).to_be_visible()
        meena.goto(f"{url}/kh/case/{case['case_id']}")
        expect(meena.get_by_label(re.compile(r"1 unread messages?"))).to_be_visible(timeout=30_000)  # the badge on the Chat tab
        walk.shot(meena, "01-unread-badge")
        meena.get_by_role("link", name=re.compile("^Chat")).click()
        expect(meena.get_by_text("Meet at the station at nine to go over the CDR (fictional).")).to_be_visible()
        expect(meena.get_by_text("SI Arun Kumar (fictional)", exact=True).first).to_be_visible()  # a team message names its writer
        meena.get_by_role("textbox", name="Message").fill("Understood: I will bring the CDR printout (fictional).")
        meena.get_by_role("textbox", name="Message").press("Enter")
        expect(meena.get_by_text("Understood: I will bring the CDR printout (fictional).")).to_be_visible()
        arun.bring_to_front()  # a page in the background does not ask for news (as for any browser tab); it does the moment it is in front
        expect(arun.get_by_text("Understood: I will bring the CDR printout (fictional).", exact=True)).to_be_visible(timeout=30_000)  # the message itself arrives by itself
        walk.shot(arun, "02-team-conversation")
        walk.step("1 a message to the whole team: an unread badge for the others, the writer named, and the answer arrives by itself")

        # ---------------------------------------------------------------- 2. a private message
        meena.get_by_role("button", name=re.compile(r"^Dev Patel \(fictional\)")).click()
        expect(meena.get_by_text("Only you and Dev Patel (fictional) see this conversation", exact=False)).to_be_visible()
        meena.get_by_role("textbox", name="Message").fill("Dev, please check the IPDR dates before the supervisor reads them (fictional).")
        meena.get_by_role("textbox", name="Message").press("Enter")
        expect(meena.get_by_text("Dev, please check the IPDR dates", exact=False)).to_be_visible()
        dev.goto(f"{url}/kh/notifications")
        expect(dev.get_by_text(re.compile("SI Meena Iyer.*wrote to you.*Dev, please check"))).to_be_visible(timeout=30_000)  # a notice, for Dev only
        dev.goto(chat)
        dev.get_by_role("button", name=re.compile(r"^SI Meena Iyer \(fictional\)")).click()
        expect(dev.get_by_text("Dev, please check the IPDR dates", exact=False)).to_be_visible()
        walk.shot(dev, "03-private-conversation")
        # nobody else sees it: Arun's conversations with Meena and with Dev, and the team conversation, have none of it
        arun.reload()
        for who in (r"^SI Meena Iyer \(fictional\)", r"^Dev Patel \(fictional\)"):
            arun.get_by_role("button", name=re.compile(who)).click()
            expect(arun.get_by_text("No messages yet")).to_be_visible()
        arun.get_by_role("button", name=re.compile("^The team")).click()
        expect(arun.get_by_text("Dev, please check the IPDR dates", exact=False)).to_have_count(0)
        walk.step("2 a private message: a notice and the conversation for Dev only; the lead and the team conversation never show it")

        # ---------------------------------------------------------------- 3. the Supervisor is not on the team
        sup.goto(f"{url}/kh/case/{case['case_id']}")
        expect(sup.get_by_text(TITLE).first).to_be_visible()
        expect(sup.get_by_role("link", name=re.compile("^Chat"))).to_have_count(0)
        sup.goto(chat)
        expect(sup.get_by_text("Chat is for the case's team")).to_be_visible()
        walk.shot(sup, "04-not-on-the-team")
        walk.step("3 the Supervisor, who oversees the case but is not on the team, has no Chat tab and no way in")

        browser.close()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--shots", type=Path, default=Path("chat-tour-shots"))
    args = parser.parse_args()
    walk = w.Walk(args.url, args.shots)
    print(f"Knight Hawk chat tour against {args.url}")
    try:
        run(walk, args)
    except Exception as error:  # noqa: BLE001 - report and keep the screenshots of what was open
        for number, page in enumerate(w.open_pages):
            try:
                page.screenshot(path=str(args.shots / f"FAILED-{number}.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        print(f"\nFAILED after {len(w.passed)} steps: {error}")
        sys.exit(1)
    print(f"\nALL {len(w.passed)} STEPS PASSED; screenshots in {args.shots}")


if __name__ == "__main__":
    main()
