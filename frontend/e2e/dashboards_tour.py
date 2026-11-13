"""Browser tour of the station and officer dashboards (phase R-5, docs/steps/16-5-dashboards.md), with fictional people.

    The Supervisor registers two cases (led by Arun); Arun puts one of them to "pending evidence".
    The Super Admin opens a second police station, then follows the stations, one station, and one officer.
    The Supervisor lands on their own station only (the other one is "not found"); Arun on his own page only; the Viewer has none.

Same set-up as walkthrough.py (throwaway database casesdb_e2e, API on 8010, web app on 5180):
    cd backend;  uv run python -m scripts.e2e_prepare   (then start the API and the web app as in docs/steps/15-4-screens.md)
    uv run --with playwright==1.64.1 python ../frontend/e2e/dashboards_tour.py --url http://127.0.0.1:5180 --shots <folder>

All names are FICTIONAL. Exit code 0 only if every step passed.
"""

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import Browser, Page, expect, sync_playwright

import walkthrough as w  # the helpers: field(), toast(), register(), Walk

FIND_CASE = """async ([tokenKey, title]) => {
  const auth = {Authorization: 'Bearer ' + sessionStorage.getItem(tokenKey)};
  const found = await (await fetch('/api/v1/cases?limit=50&q=' + encodeURIComponent(title), {headers: auth})).json();
  return found.items.find((c) => c.title === title).id;
}"""
SET_STATUS = """async ([tokenKey, caseId, value]) => {
  const auth = {Authorization: 'Bearer ' + sessionStorage.getItem(tokenKey), 'Content-Type': 'application/json'};
  const sent = await fetch(`/api/v1/cases/${caseId}/status`, {method: 'POST', headers: auth,
    body: JSON.stringify({field: 'workflow', value, reason: 'Fictional: moving the case along for the tour'})});
  return sent.status;
}"""
TITLE_1, TITLE_2 = "Dashboard tour case one (FICTIONAL)", "Dashboard tour case two (FICTIONAL)"


def row(page: Page, text: str):
    return page.get_by_role("row").filter(has_text=text).first


def run(walk: w.Walk, args: argparse.Namespace) -> None:
    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch()

        # 1. The Supervisor registers two cases; Arun, who leads them, puts the first to "pending evidence".
        sup = walk.login(browser, "kh.supervisor")
        w.register(walk, sup, TITLE_1, with_reference=False)
        sup.goto(f"{walk.url}/kh")
        w.register(walk, sup, TITLE_2, with_reference=False)
        arun = walk.login(browser, "kh.arun")
        first = arun.evaluate(FIND_CASE, [w.TOKEN_KEY, TITLE_1])
        for value in ("under_investigation", "pending_evidence"):
            assert arun.evaluate(SET_STATUS, [w.TOKEN_KEY, first, value]) == 200, value
        walk.step("1 two cases registered; one of them put to pending evidence")

        # 2. The Super Admin opens a second police station (it has no cases).
        sa = walk.login(browser, "kh.admin")
        sa.goto(f"{walk.url}/kh/people")
        sa.get_by_role("tab", name="Police stations").click()
        sa.get_by_role("button", name="Open a police station").click()
        dialog = sa.get_by_role("dialog")
        w.field(dialog, "Code").fill("PS-DASH")
        w.field(dialog, "Name").fill("Dashboard Nagar police station (fictional)")
        dialog.get_by_role("button", name="Open station").click()
        w.toast(sa, "Station PS-DASH opened")
        walk.step("2 the Super Admin opened a second police station, PS-DASH")

        # 3. The Super Admin's list of stations: figures that equal what was done.
        sa.goto(f"{walk.url}/kh")
        sa.get_by_role("link", name="Station dashboards").first.click()
        expect(sa.get_by_role("heading", name="Police stations")).to_be_visible()
        hq = row(sa, "HQ")
        expect(hq).to_be_visible()
        cells = [c.inner_text().strip() for c in hq.get_by_role("cell").all()]
        # Station, Open, Pending evidence, Pending review, Closed, New this month, Average to close, Open the longest, People
        assert cells[1:7] == ["2", "1", "0", "0", "2", "—"], cells  # two open, one pending evidence, none closed, two new, nothing to average
        dash = row(sa, "PS-DASH")
        assert [c.inner_text().strip() for c in dash.get_by_role("cell").all()][1:7] == ["0", "0", "0", "0", "0", "—"]
        walk.shot(sa, "10-stations")
        walk.step("3 the list of stations shows each station's open, pending and closed cases")

        # 4. One station: the figures, the officers.
        sa.get_by_role("link", name="HQ", exact=True).click()
        expect(sa.get_by_role("heading", name=re.compile(r"^HQ ·"))).to_be_visible()
        expect(sa.get_by_text("Pending evidence").first).to_be_visible()
        arun_row = row(sa, "SI Arun Kumar")
        expect(arun_row).to_be_visible()
        assert [c.inner_text().strip() for c in arun_row.get_by_role("cell").all()][1:5] == ["2", "2", "1", "0"]  # cases, open, pending, closed
        walk.shot(sa, "11-station")
        walk.step("4 one station: its figures, the cases open the longest, and each officer's cases")

        # 5. One officer: their cases.
        arun_row.get_by_role("link", name=re.compile("Arun")).click()
        expect(sa.get_by_role("heading", name=re.compile("Arun Kumar"))).to_be_visible()
        expect(sa.get_by_text("Pending evidence").first).to_be_visible()
        expect(sa.get_by_role("row").filter(has_text=TITLE_1)).to_be_visible()
        expect(sa.get_by_role("row").filter(has_text=TITLE_2)).to_be_visible()
        expect(row(sa, TITLE_1).get_by_text("Pending evidence")).to_be_visible()
        expect(row(sa, TITLE_1).get_by_text("Investigator (case lead)")).to_be_visible()
        walk.shot(sa, "12-officer")
        walk.step("5 one officer: progress, notes written and exhibits added, and their cases with the status of each")

        # 6. The Supervisor reaches only their own station; the other one is "not found".
        sa.goto(f"{walk.url}/kh/performance")
        station_id = sa.get_by_role("link", name="PS-DASH", exact=True).get_attribute("href")  # the address of the second station's page
        sup.goto(f"{walk.url}/kh")
        sup.get_by_role("link", name="Station dashboards").first.click()
        expect(sup.get_by_role("heading", name=re.compile(r"^HQ ·"))).to_be_visible()  # one station: straight to it
        expect(sup.get_by_role("row").filter(has_text="Asha Rao")).to_have_count(0)  # the Super Admin is above them
        sup.goto(f"{walk.url}{station_id}")
        expect(sup.get_by_text("It doesn't exist, or you don't have access to it.")).to_be_visible()
        expect(sup.get_by_role("heading", name=re.compile("PS-DASH"))).to_have_count(0)
        walk.shot(sup, "13-supervisor-other-station")
        walk.step("6 the Supervisor sees their own station; another station is not found")

        # 7. Arun sees only himself; the Viewer has no dashboards.
        arun.goto(f"{walk.url}/kh")
        arun.get_by_role("link", name="My performance").click()
        expect(arun.get_by_text("My performance").first).to_be_visible()
        expect(arun.get_by_role("heading", name=re.compile("Arun Kumar"))).to_be_visible()
        expect(arun.get_by_role("link", name="Station dashboards")).to_have_count(0)
        arun.goto(f"{walk.url}{station_id}")
        expect(arun.get_by_text("Not available for your role")).to_be_visible()
        viewer = walk.login(browser, "kh.viewer")
        expect(viewer.get_by_role("link", name=re.compile("Station dashboards|My performance"))).to_have_count(0)
        walk.shot(arun, "14-my-performance")
        walk.step("7 an Investigator sees only their own page; a Viewer has no dashboards")

        browser.close()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--shots", type=Path, default=Path("dashboards-tour-shots"))
    args = parser.parse_args()
    walk = w.Walk(args.url, args.shots)
    print(f"Knight Hawk dashboards tour against {args.url}")
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
