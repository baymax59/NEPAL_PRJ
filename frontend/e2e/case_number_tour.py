"""Browser tour of changing the case number (docs/case-management/13-plain-case-design.md, section 12, decision 20), with fictional people.

    A case is set up through the API: the Supervisor registers it, SI Arun leads it. Then, on the screens, in separate browser windows:
    1. SI Arun (the Investigator) sees the case number but no way to change it.
    2. The Supervisor clicks the pencil next to the number, types a new number and a reason; the header shows the new number and
       "Formerly KH-...", and the History tab has a numbered entry with who and why.
    3. Searching the cases for the OLD number still finds the case, and the Investigator's window shows the new number.
    4. A number that another case has is refused with a message, and nothing changes.

Same set-up as walkthrough.py (a throwaway database made by `python -m scripts.e2e_prepare`, API and web app running):
    uv run --with playwright==1.64.1 python ../frontend/e2e/case_number_tour.py --url http://127.0.0.1:5190 --shots <folder>

All names are FICTIONAL. Exit code 0 only if every step passed.
"""

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Browser, expect, sync_playwright

import chat_tour as c  # the API helpers
import walkthrough as w

NEW_NUMBER = f"PS-CYB-2026/{int(time.time()) % 100000}"  # a new one at every run (a number once used is never reused)


def run(walk: w.Walk, args: argparse.Namespace) -> None:
    url = walk.url
    ids = {name: c.api(url, "GET", "/api/auth/me", c.token_of(url, f"kh.{name}"))["id"] for name in ("supervisor", "arun")}
    sup_token = c.token_of(url, "kh.supervisor")
    first = c.api(url, "POST", "/api/v1/cases", sup_token, {
        "title": "Number tour case one (FICTIONAL)", "case_type": "cyber_fraud", "lead_investigator_id": ids["arun"], "supervisor_id": ids["supervisor"],
        "description": "FICTIONAL: a complainant reports a fake KYC message."})
    second = c.api(url, "POST", "/api/v1/cases", sup_token, {
        "title": "Number tour case two (FICTIONAL)", "case_type": "cyber_fraud", "lead_investigator_id": ids["arun"], "supervisor_id": ids["supervisor"],
        "description": "FICTIONAL: another complaint."})
    old, other = first["display_id"], second["display_id"]
    page_url = f"{url}/kh/case/{first['case_id']}"

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch()
        arun = walk.login(browser, "kh.arun")
        sup = walk.login(browser, "kh.supervisor")

        # ---------------------------------------------------------------- 1. the Investigator cannot change it
        arun.goto(page_url)
        expect(arun.get_by_text(old, exact=True).first).to_be_visible()
        expect(arun.get_by_role("button", name="Change the case number")).to_have_count(0)
        walk.step("1 the Investigator sees the case number and has no way to change it")

        # ---------------------------------------------------------------- 2. the Supervisor changes it
        sup.goto(page_url)
        sup.get_by_role("button", name="Change the case number").click()
        dialog = sup.get_by_role("dialog")
        w.field(dialog, "New case number").fill(NEW_NUMBER)
        expect(dialog.get_by_role("button", name="Change number")).to_be_disabled()  # no reason yet
        expect(dialog.get_by_role("button", name="Change number")).to_be_disabled()
        w.field(dialog, "Reason (kept in the history)").fill("The station's own file number is used from now on (fictional)")
        walk.shot(sup, "01-change-number-dialog")
        dialog.get_by_role("button", name="Change number").click()
        w.toast(sup, f"The case number is now {NEW_NUMBER}")
        expect(sup.get_by_text(NEW_NUMBER, exact=True).first).to_be_visible()
        expect(sup.get_by_text(f"Formerly {old}")).to_be_visible()
        walk.shot(sup, "02-new-number-and-formerly")
        sup.get_by_role("link", name=re.compile("^History")).click()
        expect(sup.get_by_text(f"Case number changed from {old} to {NEW_NUMBER}", exact=False).first).to_be_visible()
        walk.shot(sup, "03-history-entry")
        walk.step("2 the Supervisor changed the number with a reason: the header shows the new one and 'Formerly', the history a numbered entry")

        # ---------------------------------------------------------------- 3. the old number still finds the case
        arun.reload()
        expect(arun.get_by_text(NEW_NUMBER, exact=True).first).to_be_visible()
        expect(arun.get_by_text(f"Formerly {old}")).to_be_visible()
        arun.goto(f"{url}/kh/cases")
        arun.get_by_role("tab", name=re.compile("^All cases I can open")).click()
        arun.get_by_placeholder("Case ID or title").fill(old)
        expect(arun.get_by_role("row").filter(has_text=NEW_NUMBER)).to_have_count(1, timeout=30_000)  # the list now shows the case under its new number
        expect(arun.get_by_role("row").filter(has_text="Number tour case two")).to_have_count(0)
        walk.shot(arun, "04-search-by-the-old-number")
        walk.step("3 searching the cases for the old number still finds the case, and the Investigator sees the new number")

        # ---------------------------------------------------------------- 4. a number another case has
        sup.goto(f"{url}/kh/case/{second['case_id']}")
        sup.get_by_role("button", name="Change the case number").click()
        dialog = sup.get_by_role("dialog")
        w.field(dialog, "New case number").fill(NEW_NUMBER)
        w.field(dialog, "Reason (kept in the history)").fill("Trying a number that is taken (fictional)")
        dialog.get_by_role("button", name="Change number").click()
        w.toast(sup, "used by another case")
        sup.keyboard.press("Escape")
        expect(sup.get_by_text(other, exact=True).first).to_be_visible()  # nothing changed
        walk.shot(sup, "05-number-taken")
        walk.step("4 a number another case has is refused with a message, and the case keeps its number")

        browser.close()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--shots", type=Path, default=Path("case-number-shots"))
    args = parser.parse_args()
    walk = w.Walk(args.url, args.shots)
    print(f"Knight Hawk case-number tour against {args.url}")
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
