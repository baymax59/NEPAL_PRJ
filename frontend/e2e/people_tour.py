"""Browser tour of People and stations (phase R-4, docs/steps/16-4-people-and-stations-screens.md): the chain of who creates whom, in the
real screens, with fictional people.

    Super Admin opens a station, enters officers (one by one and from a CSV file), makes an Administrator.
    The Administrator logs in with the temporary password and is made to choose their own; makes a Supervisor.
    The Supervisor makes an Investigator, resets their password, ends their account.

Same set-up as walkthrough.py (throwaway database casesdb_e2e, API on 8010, web app on 5180):
    cd backend;  uv run python -m scripts.e2e_prepare   (then start the API and the web app as in docs/steps/15-4-screens.md)
    uv run --with playwright==1.64.1 python ../frontend/e2e/people_tour.py --url http://127.0.0.1:5180 --shots <folder>

All names are FICTIONAL. Exit code 0 only if every step passed.
"""

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import Browser, Page, expect, sync_playwright

import walkthrough as w  # the helpers: field(), choose(), toast(), Walk

OWN = "My-own-fictional-pass-1"  # a password chosen by a fictional person  # nosec B105
CSV = ("officer_number,full_name,rank,station_code,highest_role\n"
       "TOUR-SUP,Devika Tour (fictional),DSP,PS-TOUR,supervisor\n"
       "TOUR-INV,Arun Tour (fictional),Inspector,PS-TOUR,investigator\n").encode()


def fresh(browser: Browser, url: str) -> Page:
    page = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark").new_page()
    w.open_pages.append(page)
    page.goto(f"{url}/login")
    return page


def sign_in(page: Page, username: str, password: str) -> None:
    w.field(page, "Username").fill(username)
    w.field(page, "Password").fill(password)
    page.get_by_role("button", name="Log in").click()


def first_login(browser: Browser, walk: w.Walk, username: str, temporary: str, name: str) -> Page:
    """The temporary password logs in, but nothing else works until the owner chooses their own."""
    page = fresh(browser, walk.url)
    sign_in(page, username, temporary)
    expect(page.get_by_role("heading", name="Choose your own password")).to_be_visible()
    expect(page.get_by_role("link", name="People & stations")).to_have_count(0)  # no application behind it yet
    walk.shot(page, f"{name}-forced-password")
    w.field(page, "The temporary password you were given").fill(temporary)
    w.field(page, "Your new password").fill(OWN)
    w.field(page, "Repeat the new password").fill(OWN)
    page.get_by_role("button", name="Change password").click()
    w.toast(page, "Your password was changed")
    expect(page.get_by_role("link", name="Dashboard").first).to_be_visible()
    return page


def create_account(page: Page, walk: w.Walk, officer: str, shot: str) -> tuple[str, str]:
    """People tab -> Create an account for this officer. Returns (username, the temporary password shown once)."""
    page.goto(f"{walk.url}/kh/people")
    page.get_by_role("button", name="Create an account").click()
    dialog = page.get_by_role("dialog")
    w.choose(dialog, page, "Officer in the register", officer, search=officer)
    username = dialog.get_by_label(re.compile(r"^Username")).input_value()
    assert username, "the username is suggested from the officer's name"
    dialog.get_by_role("button", name="Create account").click()
    shown = page.get_by_role("dialog").filter(has_text="Temporary password for")
    expect(shown).to_be_visible()
    temporary = shown.get_by_test_id("temporary-password").inner_text().strip()
    assert re.fullmatch(r"[A-Za-z0-9]{4}(-[A-Za-z0-9]{4}){3}", temporary), temporary
    walk.shot(page, shot)
    shown.get_by_role("button", name="I have handed it over").click()
    return username, temporary


def run(walk: w.Walk, args: argparse.Namespace) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # 1. The Super Admin opens a station.
        sa = walk.login(browser, "kh.admin")
        sa.goto(f"{walk.url}/kh/people")
        sa.get_by_role("tab", name="Police stations").click()
        sa.get_by_role("button", name="Open a police station").click()
        dialog = sa.get_by_role("dialog")
        w.field(dialog, "Code").fill("PS-TOUR")
        w.field(dialog, "Name").fill("Tour Nagar police station (fictional)")
        w.field(dialog, "District").fill("Example district")
        dialog.get_by_role("button", name="Open station").click()
        w.toast(sa, "Station PS-TOUR opened")
        expect(sa.get_by_role("row").filter(has_text="PS-TOUR").first).to_be_visible()
        walk.shot(sa, "01-stations")
        walk.step("1 the Super Admin opened the police station PS-TOUR")

        # 2. Officers: one by one, then a CSV file (all or nothing).
        sa.get_by_role("tab", name="Register of officers").click()
        sa.get_by_role("button", name="Add an officer").click()
        dialog = sa.get_by_role("dialog")
        w.field(dialog, "Officer ID").fill("TOUR-ADM")
        w.field(dialog, "Full name").fill("Asha Tour (fictional)")
        w.field(dialog, "Rank").fill("DSP")
        w.choose(dialog, sa, "Station", "PS-TOUR")
        w.choose(dialog, sa, "Highest role an account may have", "Administrator")
        dialog.get_by_role("button", name="Add officer").click()
        w.toast(sa, "TOUR-ADM added to the register")
        sa.get_by_role("button", name="Import a CSV file").click()
        dialog = sa.get_by_role("dialog")
        dialog.locator('input[type="file"]').set_input_files(files=[{"name": "officers.csv", "mimeType": "text/csv", "buffer": CSV}])
        dialog.get_by_role("button", name="Check and import").click()
        expect(dialog.get_by_text("2 officers were added to the register.")).to_be_visible()
        walk.shot(sa, "02-register-imported")
        dialog.get_by_role("button", name="Close").click()
        expect(sa.get_by_role("row").filter(has_text="TOUR-SUP").first).to_be_visible()
        walk.step("2 three officers in the register: one added by hand, two from a CSV file")

        # 3. The Super Admin makes the Administrator: a temporary password, shown once.
        admin_name, admin_temp = create_account(sa, walk, "TOUR-ADM", "03-temporary-password")
        sa.goto(f"{walk.url}/kh/people")
        expect(sa.get_by_role("row").filter(has_text=f"@{admin_name}").filter(has_text="temporary password")).to_be_visible()
        walk.step("3 the Super Admin made an Administrator account; the temporary password was shown once")

        # 4. The Administrator's first login: nothing but "choose your own password" until it is done.
        admin = first_login(browser, walk, admin_name, admin_temp, "04")
        walk.step("4 the Administrator logged in with the temporary password and was made to choose their own")

        # 5. The Administrator (above the Supervisor) makes the Supervisor, at their own station.
        sup_name, sup_temp = create_account(admin, walk, "TOUR-SUP", "05-administrator-creates-supervisor")
        walk.step("5 the Administrator made a Supervisor account")

        # 6. The Supervisor's first login; they see their station and make the Investigator.
        sup = first_login(browser, walk, sup_name, sup_temp, "06")
        inv_name, inv_temp = create_account(sup, walk, "TOUR-INV", "06-supervisor-creates-investigator")
        sup.goto(f"{walk.url}/kh/people")
        sup.get_by_role("tab", name="Police stations").click()
        expect(sup.get_by_role("row").filter(has_text="PS-TOUR")).to_be_visible()
        expect(sup.get_by_role("row").filter(has_text="HQ")).to_have_count(0)  # only their own station
        walk.step("6 the Supervisor made an Investigator account and sees only their own station")

        # 7. The Investigator's first login.
        inv = first_login(browser, walk, inv_name, inv_temp, "07")
        walk.step("7 the Investigator logged in with the temporary password and chose their own")

        # 8. An Investigator may make accounts below them, but is never offered the register or the stations to change.
        inv.goto(f"{walk.url}/kh/people")
        expect(inv.get_by_role("button", name="Create an account")).to_be_visible()  # an Investigator may create the roles below them...
        inv.get_by_role("tab", name="Register of officers").click()
        expect(inv.get_by_role("button", name="Add an officer")).to_have_count(0)  # ...but never enters officers
        inv.get_by_role("tab", name="Police stations").click()
        expect(inv.get_by_role("button", name="Open a police station")).to_have_count(0)  # ...or opens stations
        walk.step("8 an Investigator may make accounts below them, but never enters officers or stations")


        # 9. Reset: the Supervisor issues a new temporary password; the Investigator must choose again.
        sup.goto(f"{walk.url}/kh/people")
        row = sup.get_by_role("row").filter(has_text=f"@{inv_name}")
        row.get_by_role("button", name=re.compile("Actions for")).click()
        sup.get_by_role("menuitem", name=re.compile("Reset password")).click()
        dialog = sup.get_by_role("dialog")
        dialog.get_by_label(re.compile("^Reason")).fill("Forgot the password (fictional)")
        dialog.get_by_role("button", name="Issue a temporary password").click()
        shown = sup.get_by_role("dialog").filter(has_text="Temporary password for")
        expect(shown).to_be_visible()
        reset_temp = shown.get_by_test_id("temporary-password").inner_text().strip()
        shown.get_by_role("button", name="I have handed it over").click()
        inv2 = fresh(browser, walk.url)
        sign_in(inv2, inv_name, OWN)  # the old password no longer works
        expect(inv2.get_by_text(re.compile("Incorrect username or password"))).to_be_visible()
        sign_in(inv2, inv_name, reset_temp)
        expect(inv2.get_by_role("heading", name="Choose your own password")).to_be_visible()
        walk.step("9 a password reset: a new temporary password, the old one stopped working, the owner chose again")

        # 10. End the account: no login; their work and the record stay.
        sup.goto(f"{walk.url}/kh/people")
        row = sup.get_by_role("row").filter(has_text=f"@{inv_name}")
        row.get_by_role("button", name=re.compile("Actions for")).click()
        sup.get_by_role("menuitem", name=re.compile("End account")).click()
        dialog = sup.get_by_role("dialog")
        dialog.get_by_label(re.compile("^Reason")).fill("Left the force (fictional)")
        dialog.get_by_role("button", name="End the account").click()
        expect(sup.get_by_role("row").filter(has_text=f"@{inv_name}").get_by_text("ended")).to_be_visible()
        walk.shot(sup, "09-account-ended")
        inv3 = fresh(browser, walk.url)
        sign_in(inv3, inv_name, reset_temp)
        expect(inv3.get_by_text(re.compile("Incorrect username or password"))).to_be_visible()
        walk.step("10 the Supervisor ended the account: no login, and the person stays in the list")

        browser.close()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--shots", type=Path, default=Path("people-tour-shots"))
    args = parser.parse_args()
    walk = w.Walk(args.url, args.shots)
    print(f"Knight Hawk people tour against {args.url}")
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
