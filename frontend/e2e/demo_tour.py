"""A read-only browser tour of the seeded demonstration case KH-2026-0001 (phase CM-8), as each of its five FICTIONAL
people sees it. It checks what each one is shown and takes the screenshots used in the user guides.

It only reads (and logs in): it creates nothing. Seed the demonstration first (backend: python -m scripts.demo_case).

Run from backend/ (whose Python has a working Playwright):
    uv run --with playwright python ../frontend/e2e/demo_tour.py --url https://localhost:8443 --shots <folder>
The passwords of the fictional accounts are read from --credentials (default: the project's .dev-credentials.txt)
and never printed. Exit code 0 only if every check passed.
"""

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Browser, Page, expect, sync_playwright

PROJECT = Path(__file__).resolve().parents[2]
LINE = re.compile(r"^(?P<user>\S+)\s+\(.*\)\s+password:\s+(?P<password>\S+)\s*$")
TITLE = "Online Banking Fraud Investigation"
expect.set_options(timeout=20_000)
seen: list[str] = []
pages: list[Page] = []


def passwords(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if (m := LINE.match(line.strip())) is not None:
            found[m["user"]] = m["password"]
    return found


class Tour:
    def __init__(self, url: str, shots: Path, credentials: dict[str, str], browser: Browser) -> None:
        self.url, self.shots, self.credentials, self.browser = url.rstrip("/"), shots, credentials, browser
        self.local = urlparse(url).hostname in ("localhost", "127.0.0.1")
        shots.mkdir(parents=True, exist_ok=True)

    def page(self) -> Page:
        # Caddy's own certificate authority (TLS=internal) isn't in the test browser's store: accepted for this computer only.
        context = self.browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark", ignore_https_errors=self.local)
        page = context.new_page()
        pages.append(page)
        return page

    def login(self, username: str) -> Page:
        page = self.page()
        page.goto(f"{self.url}/login")
        page.get_by_label(re.compile(r"^Username")).fill(username)
        page.get_by_label(re.compile(r"^Password")).fill(self.credentials[username])
        page.get_by_role("button", name="Log in").click()
        expect(page.get_by_text("Welcome,")).to_be_visible()
        return page

    def shot(self, page: Page, name: str, check: str, *, full_page: bool = True) -> None:
        page.mouse.move(2, 2)  # no tooltip over the picture
        page.wait_for_timeout(600)  # charts and graphs finish their layout
        page.screenshot(path=str(self.shots / f"{name}.png"), full_page=full_page)
        seen.append(check)
        print(f"  [ok] {check}", flush=True)


def tour(t: Tour, case: str) -> None:
    first = t.page()
    first.goto(f"{t.url}/login")
    expect(first.get_by_text("History is never rewritten")).to_be_visible()
    t.shot(first, "01-login", "the login page")

    # ---------------------------------------------------------------- Inspector Arun, Investigator 1 and the case's lead
    arun = t.login("demo.arun")
    expect(arun.get_by_role("link", name=TITLE).first).to_be_visible()
    expect(arun.get_by_text("Investigator (case lead)").first).to_be_visible()
    expect(arun.get_by_role("link", name=re.compile("tasks", re.I))).to_have_count(0)  # no task board, no "Assigned tasks" in the menu
    expect(arun.get_by_text(re.compile("open tasks", re.I))).to_have_count(0)
    t.shot(arun, "02-investigator-dashboard", f"Inspector Arun's dashboard: {case} among his cases, as its lead")
    arun.get_by_role("link", name=TITLE).first.click()
    expect(arun.get_by_text("You: Investigator (case lead)")).to_be_visible()
    url = f"{t.url}{re.search(r'/kh/case/[0-9a-f-]+', arun.url).group(0)}"
    expect(arun.get_by_text("case-information").first).to_be_visible()
    expect(arun.get_by_role("link", name="Tasks", exact=True)).to_have_count(0)  # the case has no Tasks tab
    t.shot(arun, "03-case-overview", "the case's overview: the folders made at registration, recent activity, the team, the status")
    arun.goto(f"{url}/files?folder=investigation-notes")
    expect(arun.get_by_text("Attribution of the login").first).to_be_visible()
    t.shot(arun, "04-files-and-notes", "Files: the attribution note, corrected with a new version")
    arun.get_by_text("Attribution of the login", exact=True).first.click()
    expect(arun.get_by_text("version 2 of 2")).to_be_visible()
    expect(arun.get_by_text(re.compile("INCORRECT ASSUMPTION FOUND")).first).to_be_visible()
    t.shot(arun, "04a-note-versions", "the note: both versions with the differences, and the comment recording the error")
    arun.keyboard.press("Escape")
    arun.get_by_role("button", name="Add exhibit").last.click()  # opened to show it, then cancelled: nothing is added
    expect(arun.get_by_role("dialog").get_by_text("Provenance (where it came from)", exact=False)).to_be_visible()
    t.shot(arun, "04b-add-exhibit-dialog", "the Add exhibit form: folder, provenance, legal authority", full_page=False)
    arun.get_by_role("dialog").get_by_role("button", name="Cancel").click()
    arun.goto(f"{url}/files?folder=financial-transactions")
    arun.get_by_text(re.compile("Bank transaction statement")).first.click()
    arun.get_by_role("link", name=re.compile("Open the exhibit")).click()
    expect(arun.get_by_text("File is original").first).to_be_visible()
    t.shot(arun, "05-evidence-detail", "an exhibit: integrity checks (File is original) and chain of custody")
    arun.goto(f"{url}/team")
    expect(arun.get_by_text("SI Meena Iyer (fictional)").first).to_be_visible()
    expect(arun.get_by_text("Dev Patel, analyst (fictional)").first).to_be_visible()
    t.shot(arun, "06-team", "the team: a Sub Investigator and an Analyst, added straight in by the Investigator")
    arun.goto(f"{url}/history")
    expect(arun.get_by_text("New version").first).to_be_visible()
    arun.get_by_role("button", name="Check the history").click()
    expect(arun.get_by_text("History is intact")).to_be_visible()
    t.shot(arun, "07-history", "History: every entry numbered, oldest first, and 'History is intact'")
    arun.goto(f"{url}/imports")
    expect(arun.get_by_text(re.compile(r"IMP-000\d")).first).to_be_visible()
    t.shot(arun, "08-imported-findings", "Imported findings from the fictional test source, each with its provenance")
    arun.goto(f"{url}/insights")
    expect(arun.get_by_text("Similar cases").first).to_be_visible()
    # wait for the comparison itself (it reads the whole collection), not just the tab: the picture must show the results
    expect(arun.get_by_text(re.compile(r"Past cases in the knowledge base \(\d+\)"))).to_be_visible(timeout=120_000)
    expect(arun.get_by_text(re.compile(r"Other investigations \(\d+\)"))).to_be_visible(timeout=120_000)
    t.shot(arun, "09-case-intelligence", "Insights: Case Intelligence inside the case")
    arun.goto(f"{url}/reports")
    expect(arun.get_by_text(re.compile("RPT-0001")).first).to_be_visible()
    t.shot(arun, "11-signed-report", "Reports: RPT-0001, signed, kept write-once, 'as of entry N', with its checks")

    # ---------------------------------------------------------------- SI Meena (Sub Investigator) and Dev (Analyst)
    meena = t.login("demo.meena")
    expect(meena.get_by_role("link", name=TITLE).first).to_be_visible()
    t.shot(meena, "12-sub-investigator-dashboard", "SI Meena's cases: the case, as a Sub Investigator: no invitation was needed")
    meena.goto(f"{t.url}/kh/contributions")
    expect(meena.get_by_text("Exhibits added").first).to_be_visible()
    expect(meena.get_by_text("Also credited to you, in cases you can no longer open")).to_have_count(0)  # she is still on the team
    t.shot(meena, "12b-contributions", "SI Meena's contributions: her exhibits and findings, credited to her")
    meena.goto(f"{t.url}/kh/notifications")
    expect(meena.get_by_text(re.compile("added you to .* as Sub Investigator")).first).to_be_visible()
    t.shot(meena, "13-contributor-notices", "SI Meena's notices: added to the case")
    dev = t.login("demo.dev")
    expect(dev.get_by_role("link", name=TITLE).first).to_be_visible()
    expect(dev.get_by_text("Analyst").first).to_be_visible()
    t.shot(dev, "13b-analyst-dashboard", "Dev Patel's cases: the case, as an Analyst")

    # ---------------------------------------------------------------- the supervisor
    sup = t.login("demo.supervisor")  # she supervises the case: no part on its team, every file readable
    sup.goto(f"{t.url}/kh/cases")
    sup.get_by_role("tab", name="All cases I can open").click()
    sup.get_by_role("link", name=re.compile(TITLE)).first.click()
    expect(sup.get_by_text("You oversee this case")).to_be_visible()
    expect(sup.get_by_role("button", name="Hand over the case")).to_be_visible()
    t.shot(sup, "14-supervisor-case", "the supervisor's view of the case: status, hand-over, legal holds and retention")

    # ---------------------------------------------------------------- the administrator
    admin = t.login("demo.admin")
    admin.goto(f"{t.url}/kh/admin")
    t.shot(admin, "15-admin-overview", "the administrator's overview")
    admin.goto(f"{t.url}/kh/admin/cases")
    expect(admin.get_by_role("link", name=case)).to_be_visible()
    t.shot(admin, "16-admin-cases", "all cases, in the registry")
    admin.get_by_role("link", name=case).click()
    expect(admin.get_by_text("Case registered").first).to_be_visible()
    expect(admin.get_by_text("New version").first).to_be_visible()
    t.shot(admin, "17-admin-history", "one case: its whole history, entry by entry")
    admin.get_by_role("tab", name="Access history").click()
    expect(admin.get_by_text(re.compile("Meena")).first).to_be_visible()
    t.shot(admin, "18-admin-access-history", "the access history: who joined the team, in which part, added by whom")
    admin.get_by_role("tab", name="Audit trail").click()
    admin.get_by_text("Refused and denied", exact=True).click()  # every read is recorded too: the refusals on their own
    expect(admin.get_by_text("cm.destructive_operation.rejected").first).to_be_visible()
    t.shot(admin, "19-admin-audit-trail", "the audit trail's refusals: the attempted deletions and history rewrites")
    admin.goto(f"{t.url}/kh/admin/evidence")
    expect(admin.get_by_text("EV-0006").first).to_be_visible()
    t.shot(admin, "22-admin-evidence-integrity", "evidence integrity across cases")
    admin.goto(f"{t.url}/kh/verify-report")
    t.shot(admin, "24-check-a-report", "checking a report file someone gives you")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="https://localhost:8443")
    parser.add_argument("--credentials", type=Path, default=PROJECT / ".dev-credentials.txt")
    parser.add_argument("--shots", type=Path, default=Path("demo-tour-screens"))
    parser.add_argument("--case", default="KH-2026-0001")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")  # the Windows console can't print every character of a page
    found = passwords(args.credentials)
    missing = [u for u in ("demo.admin", "demo.supervisor", "demo.arun", "demo.meena", "demo.dev") if u not in found]
    if missing:
        sys.exit(f"No password for {', '.join(missing)} in {args.credentials.name}: seed the demonstration first (scripts.demo_case).")
    started = time.time()
    print(f"Tour of the demonstration case {args.case} at {args.url} (read-only)")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            tour(Tour(args.url, args.shots, found, browser), args.case)
        except Exception as error:
            for i, page in enumerate(pages):
                try:
                    page.screenshot(path=str(args.shots / f"FAILED-{i}.png"), full_page=True)
                except Exception:  # nosec B112 - the page may already be closed
                    continue
            print(f"\nFAILED after {len(seen)} checks: {error}")
            sys.exit(1)
        finally:
            browser.close()
    print(f"\nALL {len(seen)} CHECKS PASSED in {time.time() - started:.0f} s; screenshots in {args.shots}")


if __name__ == "__main__":
    main()
