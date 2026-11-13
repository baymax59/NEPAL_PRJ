"""Browser tour of the newest account and registration features, with fictional people.

    1. A case is registered with a formatted description (bold, a numbered list) written in the compose window, and with "Reported by"
       (the person's details; "Unknown" switches the details off). The case page shows both.
    2. Officers in the register create their own login: a wrong name is refused with the one message; the right name works; the login
       starts view-only (Viewer, public clearance). One fills in the profile while signing up, one is asked on the dashboard, fills it in
       on My profile, and is not asked again; My profile shows the teams (none yet) and the official details, read-only.
    3. The Super Admin is told, raises the new login's clearance on the People screen (with a reason), and sees the contact details.

Same set-up as walkthrough.py (a throwaway database made by `python -m scripts.e2e_prepare`, API and web app running):
    uv run --with playwright==1.64.1 python ../frontend/e2e/accounts_tour.py --url http://127.0.0.1:5180 --shots <folder>

All names are FICTIONAL. Exit code 0 only if every step passed.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import Browser, Page, expect, sync_playwright

import walkthrough as w  # the helpers: Walk, choose(), field()

OWN = "My-own-fictional-pass-1"
CASE_TITLE = "Formatted description and reporter (FICTIONAL)"


def api(base: str, method: str, path: str, token: str | None = None, body=None, form=None):
    data = json.dumps(body).encode() if body is not None else (urllib.parse.urlencode(form).encode() if form else None)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(base + path, method=method, data=data, headers=headers), timeout=60) as response:
        return json.load(response)


def sign_up(page: Page, url: str, officer: str, name: str, username: str, *, email: str = "", phone: str = "") -> None:
    page.goto(f"{url}/create-account")
    page.get_by_label(re.compile(r"^Officer ID")).fill(officer)
    page.get_by_label(re.compile(r"^Full name")).fill(name)
    page.get_by_label(re.compile(r"^Username")).fill(username)
    page.get_by_label(re.compile(r"^Password")).fill(OWN)
    page.get_by_label(re.compile(r"^Repeat the password")).fill(OWN)
    if email:
        page.get_by_label(re.compile(r"^Email")).fill(email)
    if phone:
        page.get_by_label(re.compile(r"^Phone")).fill(phone)
    page.get_by_role("button", name="Create my login").click()


def visitor(browser: Browser) -> Page:
    """Somebody who is not logged in, on a page of their own (kept for the screenshot of a failed step)."""
    page = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark").new_page()
    w.open_pages.append(page)
    return page


def test_picture(path: Path) -> Path:
    """A picture made here (a plain head and shoulders), to upload as the profile photo."""
    from PIL import Image, ImageDraw  # Pillow is in the backend's environment, where the scripts run

    image = Image.new("RGB", (800, 500), (30, 90, 170))
    draw = ImageDraw.Draw(image)
    draw.ellipse((250, 60, 550, 360), fill=(240, 200, 160))
    draw.rectangle((200, 380, 600, 500), fill=(20, 50, 90))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def log_in(page: Page, url: str, username: str, password: str) -> None:
    page.goto(f"{url}/login")
    page.get_by_label(re.compile(r"^Username")).fill(username)
    page.get_by_label(re.compile(r"^Password")).fill(password)
    page.get_by_role("button", name="Log in").click()
    expect(page.get_by_text("Welcome,")).to_be_visible()


def run(walk: w.Walk, args: argparse.Namespace) -> None:
    url = walk.url
    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch()

        # ---------------------------------------------------------------- 1. a formatted description and "Reported by"
        sup = walk.login(browser, "kh.supervisor")
        sup.get_by_role("link", name="Register a case").first.click()
        w.field(sup, "Title").fill(CASE_TITLE)
        w.choose(sup, sup, "Type of case", "Cyber / online fraud")
        sup.get_by_role("button", name="Description").click()
        window = sup.get_by_role("dialog").first
        expect(window.get_by_role("toolbar", name="Text formatting")).to_be_visible()
        box = window.get_by_role("textbox", name="Description")
        box.type("Urgent: three transfers after a fake KYC message")
        box.press("Control+A")
        window.get_by_role("button", name="Bold").click()
        sup.wait_for_timeout(300)  # a person types after a click, not within a few milliseconds of it (the editor re-applies the selection a frame later)
        box.press("End")
        box.press("Enter")
        window.get_by_role("button", name="Numbered list").click()
        sup.wait_for_timeout(300)
        box.type("first transfer")
        box.press("Enter")
        box.type("second transfer")
        expect(window.get_by_role("button", name="Save")).to_be_enabled()
        walk.shot(sup, "01-description-window")
        window.get_by_role("button", name="Save").click()
        expect(window).to_be_hidden()
        w.choose(sup, sup, "Lead investigator", "SI Arun Kumar", search="Arun")
        sup.get_by_label("Unknown").check()  # "Unknown" switches the reporter's details off and clears them
        expect(sup.get_by_label("Name", exact=True)).to_be_disabled()
        sup.get_by_label("Unknown").uncheck()
        sup.get_by_label("Name", exact=True).fill("Meera Nair (fictional)")
        sup.get_by_label("Phone", exact=True).fill("+91 70000 00021")
        sup.get_by_label("Email", exact=True).fill("meera@example.invalid")
        sup.get_by_label("Address", exact=True).fill("12 Example Road")
        sup.get_by_role("button", name="Register the case").click()
        sup.get_by_role("link", name=re.compile(r"^Open ")).click()
        expect(sup.get_by_text("Case description")).to_be_visible()
        styled = sup.locator(".kh-richtext").first
        expect(styled.locator("strong").first).to_contain_text("Urgent")  # the bold text is shown as written
        expect(styled.locator("ol li")).to_have_count(2)
        about = sup.get_by_text("Reported by").first.locator("xpath=ancestor::div[contains(@class,'mantine-Paper-root')][1]")
        for shown in ("Meera Nair (fictional)", "+91 70000 00021 · meera@example.invalid", "12 Example Road"):
            expect(about.get_by_text(shown)).to_be_visible()
        walk.shot(sup, "02-case-with-description-and-reporter")
        walk.step("1 a case registered with a formatted description and Reported by; the case page shows both as written")

        # ---------------------------------------------------------------- 2. officers create their own login
        admin_token = api(url, "POST", "/api/auth/token", form={"username": "kh.admin", "password": w.PASSWORD})["access_token"]
        station = api(url, "GET", "/api/v1/people/stations", admin_token)[0]
        for number, name in (("INV-11", "Asha Verma (fictional)"), ("INV-12", "Kiran Rao (fictional)")):
            api(url, "POST", "/api/v1/people/officers", admin_token, {"officer_number": number, "full_name": name, "rank": "Inspector",
                                                                      "station_id": station["id"], "highest_role": "investigator"})
        guest = visitor(browser)
        guest.goto(f"{url}/login")
        expect(guest.get_by_role("link", name="Create your own login")).to_be_visible()
        assert not re.search(r"repositor|clone|branch|merge|commit", guest.inner_text("body"), re.I), "old wording on the log in page"
        guest.get_by_role("link", name="Create your own login").click()
        sign_up(guest, url, "INV-11", "Somebody Else", "asha.verma")
        expect(guest.get_by_text(re.compile("don't match the officer register"))).to_be_visible()
        walk.shot(guest, "03-sign-up-refused")
        sign_up(guest, url, "INV-11", "asha VERMA (fictional)", "asha.verma", email="asha@example.invalid", phone="+91 70000 00011")
        expect(guest.get_by_role("heading", name="Your login is ready")).to_be_visible()
        expect(guest.get_by_text(re.compile("view-only access"))).to_be_visible()
        walk.shot(guest, "04-sign-up-done")
        log_in(guest, url, "asha.verma", OWN)
        me = api(url, "GET", "/api/auth/me", api(url, "POST", "/api/auth/token", form={"username": "asha.verma", "password": OWN})["access_token"])
        assert (me["org_role"], me["clearance"]) == ("viewer", "public"), me  # the least access there is
        guest.wait_for_timeout(800)
        assert guest.get_by_text("Complete your profile").count() == 0  # the profile was filled in while signing up
        walk.step("2 a wrong name is refused with one message; the right name creates a view-only login, profile filled in at sign-up")

        second = visitor(browser)
        sign_up(second, url, "INV-12", "Kiran Rao (fictional)", "kiran.rao")
        expect(second.get_by_role("heading", name="Your login is ready")).to_be_visible()
        log_in(second, url, "kiran.rao", OWN)
        expect(second.get_by_text("Complete your profile")).to_be_visible()  # no profile yet: the dashboard asks
        walk.shot(second, "05-dashboard-asks-for-the-profile")
        second.get_by_role("link", name="Open my profile").click()
        expect(second.get_by_role("heading", name="My profile")).to_be_visible()
        expect(second.get_by_text("Not on any team yet")).to_be_visible()
        for official in ("INV-12", "Inspector", "Viewer", "Public"):
            expect(second.get_by_text(official, exact=True).first).to_be_visible()  # the register's details, only shown
        second.get_by_label(re.compile(r"^Email")).fill("kiran@example.invalid")
        second.get_by_label(re.compile(r"^Phone")).fill("+91 70000 00012")
        second.get_by_label(re.compile(r"^Job title")).fill("Investigating officer, cyber cell")
        walk.shot(second, "06-my-profile")
        second.get_by_role("button", name="Save my profile").click()
        expect(second.get_by_text("Your profile is saved")).to_be_visible()
        second.goto(f"{url}/kh")
        expect(second.get_by_text("Welcome,")).to_be_visible()
        second.wait_for_timeout(800)
        assert second.get_by_text("Complete your profile").count() == 0  # saved once: not asked again
        walk.step("3 no profile at sign-up: the dashboard asks; My profile saves it and shows the teams and the read-only details")

        # the photo: chosen on My profile, drawn again by the server as a small square, shown in the top bar and (below) in the People list
        second.goto(f"{url}/kh/profile")
        expect(second.get_by_role("button", name="Upload a photo")).to_be_visible()
        second.locator('input[type="file"]').set_input_files(str(test_picture(args.shots / "test-photo.png")))
        expect(second.get_by_text("Your photo is saved")).to_be_visible()
        expect(second.get_by_role("button", name="Remove photo")).to_be_visible()
        expect(second.locator("header img")).to_have_count(1)
        walk.shot(second, "08-profile-with-photo")
        walk.step("3b a profile photo uploaded on My profile appears in the top bar")

        # ---------------------------------------------------------------- 3. the Super Admin is told and raises the clearance
        sa = walk.login(browser, "kh.admin")
        sa.goto(f"{url}/kh/notifications")
        expect(sa.get_by_text(re.compile("Kiran Rao.*created their own login")).first).to_be_visible()
        sa.goto(f"{url}/kh/people")
        expect(sa.get_by_text("Investigating officer, cyber cell · kiran@example.invalid · +91 70000 00012")).to_be_visible()
        row = sa.get_by_role("row").filter(has_text="kiran.rao")
        row.get_by_role("button", name=re.compile("^Actions for")).click()
        sa.get_by_role("menuitem", name="Change clearance…").click()
        w.choose(sa.get_by_role("dialog"), sa, "New clearance", "Restricted")
        sa.get_by_label(re.compile("^Reason")).fill("Works on restricted cases (fictional)")
        walk.shot(sa, "07-change-clearance")
        sa.get_by_role("button", name="Change clearance").click()
        expect(sa.get_by_text(re.compile("now has Restricted clearance"))).to_be_visible()
        raised = api(url, "GET", "/api/auth/me", api(url, "POST", "/api/auth/token", form={"username": "kiran.rao", "password": OWN})["access_token"])
        assert raised["clearance"] == "restricted", raised
        sa.goto(f"{url}/kh/people")
        expect(sa.get_by_role("row").filter(has_text="kiran.rao").locator("img")).to_have_count(1)  # the photo, next to the name
        walk.step("4 the Super Admin was told, saw the contact details and the photo, and raised the new login's clearance with a reason")

        browser.close()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--shots", type=Path, default=Path("accounts-tour-shots"))
    args = parser.parse_args()
    walk = w.Walk(args.url, args.shots)
    print(f"Knight Hawk accounts and registration tour against {args.url}")
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
