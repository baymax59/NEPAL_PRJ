"""Browser walk-through of the Knight Hawk screens on the plain case design: registering a case (its folders are made at once), the
case page and its tabs, notes with versions, exhibits and their integrity check, folders, the team (a Sub Investigator and an Analyst
added straight in), the history and its check, the Supervisor's approval, links, signed reports, Case Intelligence inside a case,
findings added by connected systems, governance, a hand-over and two-step verification, with fictional data. The assistant step needs
Ollama running with the chat model.

1. Prepare the throwaway database (only ever casesdb_e2e):      cd backend;  uv run python -m scripts.e2e_prepare
2. Start the API on it, and the web app pointing at that API (see docs/steps/15-4-screens.md).
3. Run (from backend/, whose Python has a working Playwright):
       uv run --with playwright python ../frontend/e2e/walkthrough.py --url http://127.0.0.1:5180 --shots <folder>

All people, cases and evidence are FICTIONAL. Exit code 0 only if every step passed.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import pyotp
from playwright.sync_api import Browser, Locator, Page, expect, sync_playwright

PASSWORD = "Fictional-walkthrough-1"  # the test-only password of scripts/e2e_prepare.py  # nosec B105
PNG = b"\x89PNG\r\n\x1a\n" + b"FICTIONAL TEST IMAGE: a WhatsApp message asking for an OTP"
CASE_A = "Online banking fraud (FICTIONAL)"
CASE_B = "Second online fraud (FICTIONAL)"
FIR = ("First Information Report (FICTIONAL TEST DOCUMENT). On 3 March 2026 the complainant received a call from a person "
       "claiming to be a bank officer, who asked for the OTP sent to her phone 98450 12345. On 4 March 2026 three transfers of "
       "INR 85000 each were made by UPI to a mule account. Offences under Section 318(4) of the BNS and Section 66D of the "
       "Information Technology Act, 2000 are reported.").encode()
TOKEN_KEY = "case-search.token"  # the browser storage key that holds the login, not a secret  # nosec B105
# A finding an outside system sends through the integration contract: it names the suspect's phone number,
# which the CDR result of the test source also names in the other case. FICTIONAL.
ALERT_FOR_CASE_B = {
    "item_type": "alert", "source_record_id": "AL-2026-0207",
    "source_hash": "sha256:" + "7f" * 32,
    "title": "Repeated calls from a number reported for fraud (FICTIONAL)",
    "summary": "FICTIONAL. The alerting system flagged 37 calls in one hour from +91 70000 00042, a number already reported in a fraud case.",
    "observed_at": "2026-03-09T16:20:00+05:30",
    "identifiers": [{"type": "phone", "value": "+91 70000 00042"}],
    "details": {"rule": "FICT-RULE-04 call bursts from a reported number", "severity": "medium", "calls": 37},
}
SEND_FINDING = """async ([caseId, key, tokenKey, finding]) => {
  const auth = {Authorization: 'Bearer ' + sessionStorage.getItem(tokenKey)};
  const sent = await fetch('/api/v1/integrations/add-to-case', {
    method: 'POST',
    headers: {...auth, 'Content-Type': 'application/json', 'X-Integration-Key': key},
    body: JSON.stringify({case_id: caseId, ...finding}),
  });
  return [sent.status, await sent.text()];
}"""
STATUS_OF = """async ([url, method, key]) => (await fetch(url, {method, headers: {Authorization: 'Bearer ' + sessionStorage.getItem(key)}})).status"""

expect.set_options(timeout=20_000)
passed: list[str] = []
open_pages: list[Page] = []  # screenshotted if a step fails


class Walk:
    def __init__(self, url: str, shots: Path) -> None:
        self.url, self.shots = url.rstrip("/"), shots
        shots.mkdir(parents=True, exist_ok=True)

    def shot(self, page: Page, name: str) -> None:
        page.wait_for_timeout(400)  # let charts finish their layout
        page.screenshot(path=str(self.shots / f"{name}.png"), full_page=True)

    def step(self, name: str) -> None:
        print(f"  [ok] {name}", flush=True)
        passed.append(name)

    def login(self, browser: Browser, username: str) -> Page:
        page = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark").new_page()
        page.goto(f"{self.url}/login")
        field(page, "Username").fill(username)
        field(page, "Password").fill(PASSWORD)
        page.get_by_role("button", name="Log in").click()
        open_pages.append(page)
        expect(page.get_by_text("Welcome,")).to_be_visible()
        return page


def field(scope: Page | Locator, label: str) -> Locator:
    """The input with this label; required fields add an asterisk to it."""
    return scope.get_by_label(re.compile(rf"^{re.escape(label)}(\s*\*)?$"))


def write_description(page: Page, text: str) -> None:
    """The case's description is written in a small email-style window opened by the Description button."""
    page.get_by_role("button", name="Description").click()
    window = page.get_by_role("dialog")
    window.get_by_role("textbox", name="Description").fill(text)
    window.get_by_role("button", name="Save").click()
    expect(window).to_be_hidden()


def choose(scope: Page | Locator, page: Page, label: str, option: str, search: str | None = None) -> None:
    """Pick an option of a Mantine select (typing first when it is searchable). Options open outside dialogs."""
    name = re.compile(rf"^{re.escape(label)}(\s*\*)?$")
    box = scope.get_by_role("combobox", name=name)
    if box.count() == 0:  # a multi-select: its search field carries the label
        box = field(scope, label).first
    box.click()
    if search is not None:
        box.fill(search)
    page.get_by_role("option", name=option).first.click()  # substring match


def toast(page: Page, text: str | re.Pattern) -> None:
    """A confirmation message (a plain string matches part of the text)."""
    expect(page.locator(".mantine-Notification-root").filter(has_text=text).first).to_be_visible()


def tab(page: Page, name: str) -> None:
    """Open a tab of the case page and wait until the address has changed."""
    path = "" if name == "Overview" else "/" + name.lower()
    page.get_by_role("link", name=name, exact=True).first.click()
    page.wait_for_url(re.compile(rf"/kh/case/[0-9a-f-]+{path}(\?.*)?$"))


def case_url(page: Page, base: str) -> str:
    """The address of the case whose page is open (without any tab)."""
    return base + re.search(r"/kh/case/[0-9a-f-]+", page.url).group(0)


def add_fir(page: Page, case: str) -> None:
    """Add the fictional FIR copy as an exhibit (text: Case Intelligence reads it)."""
    page.goto(f"{case}/files")
    page.get_by_role("button", name="Add exhibit").first.click()
    dialog = page.get_by_role("dialog")
    dialog.locator('input[type="file"]').set_input_files(files=[{"name": "fir-complaint.txt", "mimeType": "text/plain", "buffer": FIR}])
    field(dialog, "Title").fill("FIR copy (fictional)")
    dialog.get_by_role("button", name="Add to the case").click()
    toast(page, "added to the case")


def register(walk: Walk, page: Page, title: str, with_reference: bool) -> str:
    page.get_by_role("link", name="Register a case").first.click()
    field(page, "Title").fill(title)
    choose(page, page, "Type of case", "Cyber / online fraud")
    expect(page.get_by_text("Folders made for the case")).to_be_visible()
    write_description(page, "Fictional: a complainant reports three unauthorised transfers, INR 250000 in total, after sharing an OTP.")
    choose(page, page, "Lead investigator", "SI Arun Kumar", search="Arun")
    choose(page, page, "Supervisor (recommended)", "Devika", search="Devika")
    if with_reference:
        field(page, "Number").fill("0123/2026")
        walk.shot(page, "05-new-case-registration")
    page.get_by_role("button", name="Register the case").click()
    expect(page.get_by_text("Case registered", exact=True).first).to_be_visible()
    return re.search(r"[A-Z]{2,10}-\d{4}-\d{4}", page.locator("h2").first.inner_text()).group(0)


def registered_case_id(page: Page) -> str:
    """The id of the case just registered: the address its "Open ..." button leads to."""
    return page.get_by_role("link", name=re.compile(r"^Open [A-Z]")).get_attribute("href").split("/kh/case/")[1]


def change_status(page: Page, option: str, reason: str) -> None:
    page.get_by_role("button", name="Change case status").click()
    dialog = page.get_by_role("dialog")
    choose(dialog, page, "New status", option)
    field(dialog, "Reason (kept in the history)").fill(reason)
    dialog.get_by_role("button", name="Change", exact=True).click()
    toast(page, "Status changed and recorded")


def steps(walk: Walk, browser: Browser) -> None:

    first = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    open_pages.append(first)
    first.goto(f"{walk.url}/login")
    expect(first.get_by_text("History is never rewritten")).to_be_visible()
    walk.shot(first, "01-login")
    walk.step("1 login screen")

    # ---------------------------------------------------------------- the supervisor registers the case
    sup = walk.login(browser, "kh.supervisor")
    case_a = register(walk, sup, CASE_A, with_reference=True)
    expect(sup.get_by_text("10 folders made for you")).to_be_visible()
    expect(sup.get_by_text("SI Arun Kumar (fictional) leads the case")).to_be_visible()
    id_a = registered_case_id(sup)
    walk.shot(sup, "05b-case-registered")
    walk.step(f"5 new case registration: {case_a} with its ten folders made at once, and the Investigator as its lead")

    # ---------------------------------------------------------------- the lead investigator works in the case
    arun = walk.login(browser, "kh.arun")
    expect(arun.get_by_role("link", name=CASE_A).first).to_be_visible()
    expect(arun.get_by_text("Investigator (case lead)").first).to_be_visible()
    walk.shot(arun, "03-investigator-dashboard")
    walk.step("3 investigator dashboard: My cases, with his part in the case")
    arun.get_by_role("link", name=CASE_A).first.click()
    expect(arun.get_by_role("heading", name=CASE_A)).to_be_visible()
    for name in ("Overview", "Files", "Team", "History", "Links", "Reports", "Insights", "Imports"):
        expect(arun.get_by_role("link", name=name, exact=True).first).to_be_visible()
    for gone in ("Branches", "Commits", "Review requests", "Investigation graph"):
        expect(arun.get_by_role("link", name=gone, exact=True)).to_have_count(0)
    expect(arun.get_by_text("case-information").first).to_be_visible()
    a_url = case_url(arun, walk.url)
    assert a_url.endswith(id_a), (a_url, id_a)
    walk.shot(arun, "06-case-overview")
    walk.step("6 case overview: the folders made at registration, recent activity, the team, the facts")

    tab(arun, "Files")
    arun.get_by_role("button", name="New note").first.click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Title").fill("Initial assessment (fictional)")
    field(dialog, "Text").fill("The complainant shared an OTP during a call (fictional).\nThree transfers followed within ten minutes.")
    dialog.get_by_role("button", name="Add to the case").click()
    toast(arun, "Added to the case")
    arun.get_by_role("button", name="Add exhibit").first.click()
    dialog = arun.get_by_role("dialog")
    dialog.locator('input[type="file"]').set_input_files(files=[{"name": "whatsapp-message.png", "mimeType": "image/png", "buffer": PNG}])
    field(dialog, "Title").fill("WhatsApp message asking for the OTP (fictional)")
    field(dialog, "Source").fill("Complainant's phone (fictional)")
    dialog.get_by_role("button", name="Add to the case").click()
    toast(arun, r"EV-0001 added to the case")
    arun.goto(f"{a_url}/files?folder=digital-evidence")  # the exhibit's folder
    expect(arun.get_by_text("WhatsApp message asking for the OTP (fictional)").first).to_be_visible()
    walk.shot(arun, "07-files")
    walk.step("7 files: a note and an exhibit written straight into the case, in their folders")

    arun.get_by_text("WhatsApp message asking for the OTP (fictional)").first.click()
    arun.get_by_role("link", name=re.compile("Open the exhibit")).click()
    arun.get_by_role("button", name="Verify integrity now").click()
    expect(arun.get_by_text("File is original").first).to_be_visible()
    walk.shot(arun, "08-evidence-detail-and-integrity")
    walk.step("8 evidence detail: integrity verified (File is original), chain of custody")

    arun.goto(f"{a_url}/files")
    arun.get_by_role("button", name="New folder").click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Folder name").fill("telecom-requisitions")
    dialog.get_by_role("button", name="Add folder").click()
    toast(arun, "Folder telecom-requisitions added")
    expect(arun.get_by_text("telecom-requisitions").first).to_be_visible()
    walk.shot(arun, "09-new-folder")
    walk.step("9 a folder added by the Investigator (permanent: it can't be renamed or removed)")

    # ---------------------------------------------------------------- the team: added straight in
    tab(arun, "Team")
    arun.get_by_role("button", name="Add team member").click()
    dialog = arun.get_by_role("dialog")
    choose(dialog, arun, "Colleague", "Meena", search="Meena")
    expect(dialog.get_by_text("Sub Investigator").first).to_be_visible()
    walk.shot(arun, "15a-add-team-member")
    dialog.get_by_role("button", name="Add to the team").click()
    toast(arun, "is now on the team")
    arun.get_by_role("button", name="Add team member").click()
    dialog = arun.get_by_role("dialog")
    choose(dialog, arun, "Colleague", "Dev", search="Dev")
    choose(dialog, arun, "Part in the case", "Analyst")
    dialog.get_by_role("button", name="Add to the team").click()
    toast(arun, "is now on the team")
    expect(arun.get_by_text("SI Meena Iyer (fictional)").first).to_be_visible()
    expect(arun.get_by_text("Dev Patel (fictional)").first).to_be_visible()
    expect(arun.get_by_role("button", name="Take off the team")).to_have_count(2)  # never for the lead
    walk.shot(arun, "15-team")
    walk.step("15 team: a Sub Investigator and an Analyst added by the Investigator, at once: no invitation, no approval")

    # ---------------------------------------------------------------- the Sub Investigator reads the Investigator's note and comments on it
    meena = walk.login(browser, "kh.meena")
    expect(meena.get_by_role("link", name=CASE_A).first).to_be_visible()
    expect(meena.get_by_text("Sub Investigator").first).to_be_visible()
    meena.goto(f"{a_url}/files")
    meena.get_by_text("Initial assessment (fictional)", exact=True).first.click()
    meena.get_by_label("Comment").fill("Read. I will start on the CDR requests (fictional).")
    meena.get_by_role("button", name="Comment", exact=True).click()
    expect(meena.get_by_text("I will start on the CDR requests").first).to_be_visible()
    expect(arun.locator(".mantine-Indicator-indicator").first).to_be_visible(timeout=30_000)
    walk.step("live notices: the investigator's bell updated without reloading when the Sub Investigator commented on the note")
    meena.keyboard.press("Escape")

    meena.goto(f"{a_url}/files")
    meena.get_by_role("button", name="New note").first.click()
    dialog = meena.get_by_role("dialog")
    choose(dialog, meena, "Kind", "Analysis")
    field(dialog, "Title").fill("CDR leads (fictional)")
    field(dialog, "Text").fill("Three numbers called the complainant before the transfers (fictional).")
    dialog.get_by_role("button", name="Add to the case").click()
    toast(meena, "Added to the case")
    expect(meena.get_by_role("button", name="Add team member")).to_have_count(0)  # not hers to do
    walk.step("a Sub Investigator adds an analysis straight into the case")

    # ---------------------------------------------------------------- the history and its check
    tab(arun, "History")
    expect(arun.get_by_text("Case registered").first).to_be_visible()
    arun.get_by_role("button", name="Check the history").click()
    expect(arun.get_by_text("History is intact")).to_be_visible()
    walk.shot(arun, "10-history")
    walk.step("10 history: every entry numbered, in order, and the check says 'History is intact'")

    # ---------------------------------------------------------------- the supervisor approves
    tab(arun, "Overview")
    change_status(arun, "Under investigation", "Investigation under way (fictional)")
    change_status(arun, "Pending review", "The findings are in: ready for the supervisor's review (fictional)")
    sup.goto(a_url)
    expect(sup.get_by_text("Pending review").first).to_be_visible()
    expect(sup.get_by_text("You oversee this case")).to_be_visible()
    change_status(sup, "Approved for reporting", "Checked against the exhibits. Approved (fictional).")
    walk.shot(sup, "17-supervisor-approval")
    walk.step("17 the supervisor reads the case and approves it for reporting, with a reason (a numbered entry of the history)")

    # ---------------------------------------------------------------- a new version, and withdrawing
    arun.goto(f"{a_url}/files?folder=investigation-notes")
    arun.get_by_text("Initial assessment (fictional)", exact=True).first.click()
    arun.get_by_role("button", name="New version").click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Text").fill("The complainant shared an OTP during a call (fictional).\nThree transfers followed within ten minutes.\nThe bank was written to.")
    field(dialog, "What changed").fill("Added the letter to the bank (fictional)")
    dialog.get_by_role("button", name="Save new version").click()
    toast(arun, "Saved as a new version")
    expect(arun.get_by_text("version 2 of 2")).to_be_visible()
    expect(arun.get_by_text("Added the letter to the bank (fictional)")).to_be_visible()
    walk.shot(arun, "11-note-versions")
    walk.step("11 a note corrected with a new version: both versions stay, with the differences and why")
    arun.keyboard.press("Escape")

    arun.get_by_role("button", name="New note").first.click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Title").fill("Entered by mistake (fictional)")
    field(dialog, "Text").fill("Wrong case.")
    dialog.get_by_role("button", name="Add to the case").click()
    toast(arun, "Added to the case")
    arun.get_by_text("Entered by mistake (fictional)", exact=True).first.click()
    arun.get_by_role("button", name="Withdraw").click()
    dialog = arun.get_by_role("dialog", name=re.compile("Withdraw Entered by mistake"))
    dialog.get_by_role("textbox").fill("Entered in the wrong case (fictional)")
    dialog.get_by_role("button", name="Withdraw").click()
    toast(arun, "Withdrawn")
    expect(arun.locator(".mantine-Drawer-overlay")).to_have_count(0)  # the side panel has closed
    expect(arun.get_by_text("Entered by mistake (fictional)", exact=True)).to_have_count(0)  # gone for the team, the Investigator included
    expect(arun.get_by_role("switch", name="Show withdrawn files")).to_have_count(0)
    walk.shot(arun, "12-withdrawn-file")
    sup.goto(f"{a_url}/files")  # the supervisor keeps it in view, in red, and has nothing to withdraw with
    row = sup.get_by_role("row").filter(has_text="Entered by mistake (fictional)")
    expect(row).to_be_visible()
    expect(row.get_by_text("withdrawn", exact=True)).to_be_visible()
    expect(row.get_by_text("Entered in the wrong case (fictional)")).to_be_visible()
    row.get_by_text("Entered by mistake (fictional)", exact=True).click()
    expect(sup.get_by_role("button", name="Withdraw")).to_have_count(0)
    walk.shot(sup, "12b-withdrawn-file-for-the-supervisor")
    sup.keyboard.press("Escape")
    walk.step("12 a wrong file withdrawn with a reason: gone for the team, still there in red for the supervisor, who cannot withdraw anything")

    # ---------------------------------------------------------------- links to another case
    case_b = register(walk, sup, CASE_B, with_reference=False)
    id_b = registered_case_id(sup)
    b_url = f"{walk.url}/kh/case/{id_b}"
    arun.goto(f"{a_url}/links")
    arun.get_by_role("button", name="Link a case").click()
    dialog = arun.get_by_role("dialog")
    choose(dialog, arun, "Case", CASE_B, search="Second")
    choose(dialog, arun, "How are they related?", "Same person of interest")
    field(dialog, "Reason").fill("Fictional: the same mule account receives the money in both cases.")
    dialog.get_by_role("button", name="Link", exact=True).click()
    toast(arun, "Case linked")
    expect(arun.locator(".react-flow__node").nth(1)).to_be_visible()
    walk.shot(arun, "18-case-links-and-relationship-graph")
    walk.step(f"18 case links and relationship graph ({case_a} to {case_b})")

    # ---------------------------------------------------------------- reports
    arun.goto(f"{a_url}/reports")
    expect(arun.get_by_text("KNIGHT HAWK · CASE REPORT")).to_be_visible()
    expect(arun.get_by_text(re.compile("not automatically admissible")).first).to_be_visible()
    arun.get_by_role("button", name="Generate a signed PDF").click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Purpose").fill("Fictional: report on the case for the supervisor's review.")
    dialog.get_by_role("button", name="Generate", exact=True).click()
    toast(arun, re.compile(r"RPT-0001 version 1 generated, as of entry \d+"))
    with arun.expect_download() as downloaded:
        arun.get_by_role("button", name="Download RPT-0001 version 1").click()
    report_file = walk.shots / "RPT-0001-v1.pdf"
    downloaded.value.save_as(report_file)
    walk.shot(arun, "19-report-generation")
    walk.step("19 report generation: a signed PDF (RPT-0001 version 1) 'as of entry N', with provenance and integrity, kept write-once")
    arun.goto(f"{walk.url}/kh/verify-report")
    arun.locator('input[type="file"]').set_input_files(str(report_file))
    arun.get_by_role("button", name="Check", exact=True).click()
    expect(arun.get_by_text("Genuine: exactly the report Knight Hawk generated")).to_be_visible()
    walk.shot(arun, "19b-report-checked")
    walk.step("17 acceptance: the downloaded report checked byte for byte against the recorded report (genuine)")

    # ---------------------------------------------------------------- Case Intelligence inside the case
    add_fir(arun, a_url)
    add_fir(arun, b_url)  # the same file in the other case: read once, and a strong link between them

    arun.goto(f"{a_url}/insights")
    expect(arun.get_by_text(re.compile("Read for you:"))).to_be_visible()
    past = arun.locator(".mantine-Paper-root").filter(has=arun.get_by_role("link", name="FICT-SC-0001", exact=True)).last
    expect(past).to_be_visible(timeout=90_000)
    expect(arun.get_by_text("Same file").first).to_be_visible()
    expect(arun.get_by_role("link", name="FICT-SC-0002", exact=True)).to_have_count(0)  # the unrelated past case isn't shown
    walk.shot(arun, "21-similar-cases")
    past.get_by_role("button", name="Link").click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Reason").fill("Fictional: the same bank-officer script and a mule account, as in this past case.")
    dialog.get_by_role("button", name="Link", exact=True).click()
    toast(arun, "Case linked")
    expect(past.get_by_text("Linked", exact=True)).to_be_visible()
    walk.step("similar cases: a past case and another investigation (the same file), with why; the past case linked")

    arun.get_by_role("tab", name="Search").click()
    field(arun, "Search this case").fill('"98450 12345"')
    arun.get_by_role("button", name="Search", exact=True).click()
    expect(arun.locator("mark").filter(has_text="98450").first).to_be_visible()
    walk.shot(arun, "22-search-inside-the-case")
    walk.step("search inside the case: the phone number found and highlighted")

    arun.get_by_role("tab", name="Timeline").click()
    arun.get_by_role("button", name="Build the timeline").click()
    toast(arun, "Timeline version 1 saved")
    expect(arun.get_by_text(re.compile("received a call from a person")).first).to_be_visible()
    walk.shot(arun, "23-reconstructed-timeline")
    walk.step("reconstructed timeline: dates from the documents, saved as version 1 of the timeline note")

    arun.get_by_role("tab", name="Offence sections").click()
    expect(arun.get_by_text("Section 318 BNS").first).to_be_visible()
    expect(arun.get_by_text("Cheating", exact=True).first).to_be_visible()
    expect(arun.get_by_text("Section 420 IPC").first).to_be_visible()  # cited by the similar past case
    walk.shot(arun, "24-offence-sections")
    walk.step("offence sections: cited in the FIR, and cited by the similar past case")

    arun.get_by_role("tab", name="Assistant").click()
    field(arun, "Your question").fill("On which dates were the transfers made, and to what kind of account?")
    arun.get_by_role("button", name="Ask", exact=True).click()
    expect(arun.get_by_text(re.compile(r"Sources given to the assistant \(\d+, [1-9]\d* cited\)"))).to_be_visible(timeout=360_000)
    walk.shot(arun, "25-case-assistant")
    walk.step("case assistant: an answer from the case as it stands, citing exhibit, version and page")

    # ---------------------------------------------------------------- integrations
    admin = walk.login(browser, "kh.admin")
    admin.goto(f"{walk.url}/kh/admin/integrations")
    admin.get_by_role("button", name="Add the fictional test source").click()
    shown = admin.get_by_role("dialog")
    key = shown.locator("pre").filter(has_text="khi_").first.inner_text().strip()
    walk.shot(admin, "26-integration-source-key-shown-once")
    shown.get_by_role("button", name="I have copied it").click()
    expect(admin.get_by_text("fictional test source", exact=True).first).to_be_visible()
    walk.shot(admin, "27-integration-sources")
    walk.step("integration sources: the fictional test source registered by an administrator, its key shown once")

    arun.goto(f"{a_url}/imports")
    arun.get_by_role("button", name="Add from a source").click()
    dialog = arun.get_by_role("dialog")
    dialog.get_by_role("button", name="Add CDR-RES-2026-017-01 to the case").click()
    toast(arun, re.compile(r"IMP-0001 added to the case"))
    dialog.get_by_role("button", name="Add IPDR-RES-2026-017-02 to the case").click()
    toast(arun, re.compile(r"IMP-0002 added to the case"))
    walk.shot(arun, "28-add-from-a-source")
    arun.keyboard.press("Escape")
    arun.get_by_role("button", name=re.compile("Open IMP-0001")).click()
    drawer = arun.get_by_role("dialog")
    expect(drawer.get_by_text("Requisition FICT/CYB/2026/017", exact=False).first).to_be_visible()
    expect(drawer.get_by_text("CDR-RES-2026-017-01", exact=True)).to_be_visible()
    walk.shot(arun, "29-imported-finding-provenance")
    arun.keyboard.press("Escape")
    walk.step("add to case: a CDR and an IPDR result from the test source, each a permanent record with its provenance, in the history")

    status, answer = arun.evaluate(SEND_FINDING, [id_b, key, TOKEN_KEY, ALERT_FOR_CASE_B])
    if status != 201:
        raise RuntimeError(f"the integration contract answered {status}: {answer[:300]}")
    arun.goto(f"{a_url}/imports?view=indicators")
    row = arun.locator("tr").filter(has_text="+917000000042")
    expect(row.get_by_role("link", name=case_b)).to_be_visible()
    expect(row.get_by_text("linked", exact=True)).to_be_visible()
    walk.shot(arun, "30-indicators-across-cases")
    walk.step(f"the contract over HTTP (source key + login) adds an alert to {case_b}; the suspect's phone is found in both cases, already linked")

    # ---------------------------------------------------------------- the administrator
    admin.goto(f"{walk.url}/kh/admin")
    expect(admin.locator(".recharts-surface").first).to_be_visible()
    walk.shot(admin, "02-admin-dashboard")
    walk.step("2 admin dashboard")
    admin.goto(f"{walk.url}/kh/admin/cases")
    expect(admin.get_by_role("link", name=case_a)).to_be_visible()
    walk.shot(admin, "04-all-cases-registry")
    walk.step("4 all cases registry")
    admin.get_by_role("link", name=case_a).click()
    expect(admin.get_by_text("Case registered").first).to_be_visible()
    expect(admin.get_by_text("Approved for reporting").first).to_be_visible()
    walk.shot(admin, "14-admin-case-history")
    walk.step("14 one case for the administrator: its whole history, in order")

    for method, url in (("DELETE", f"/api/v1/cases/{id_a}"), ("PATCH", f"/api/v1/cases/{id_a}/history/1")):
        refused = admin.evaluate(STATUS_OF, [url, method, TOKEN_KEY])
        if refused != 405:
            raise RuntimeError(f"{method} {url} answered {refused}, not 405")
    admin.get_by_role("tab", name="Audit trail").click()
    expect(admin.get_by_text("cm.destructive_operation.rejected").first).to_be_visible()
    expect(admin.get_by_text("cm.integration.import").first).to_be_visible()
    walk.shot(admin, "20-audit-history")
    walk.step("20 audit history: the attempted deletion and history rewrite were refused (405) and recorded")
    admin.get_by_role("tab", name="Access history").click()
    expect(admin.get_by_text("became Analyst").first).to_be_visible()
    walk.shot(admin, "14b-admin-access-history")
    walk.step("the access history shows who joined the team, in which part, added by whom")

    admin.goto(f"{walk.url}/kh/admin/evidence")
    expect(admin.get_by_text("EV-0001").first).to_be_visible()
    walk.shot(admin, "admin-evidence-integrity")
    admin.goto(f"{walk.url}/kh/admin/activity")
    expect(admin.get_by_text(case_a).first).to_be_visible()
    walk.shot(admin, "admin-investigation-activity")
    walk.step("admin evidence integrity and investigation activity")

    sup.goto(b_url)
    sup.get_by_role("button", name="Place a hold").click()
    dialog = sup.get_by_role("dialog")
    field(dialog, "Reason").fill("Fictional: a preservation order was received while the appeal is pending.")
    field(dialog, "Order or instruction (optional)").fill("Order FICT/2026/7 (fictional)")
    dialog.get_by_role("button", name="Place the hold").click()
    toast(sup, "Legal hold placed")
    expect(sup.get_by_text("Under a legal hold")).to_be_visible()
    walk.shot(sup, "32-legal-hold")
    walk.step(f"legal hold placed on {case_b} by the supervisor: it can't be archived, nor a disposal approved, until released")

    # ---------------------------------------------------------------- hand over a case
    sup.get_by_role("button", name="Hand over the case").click()
    dialog = sup.get_by_role("dialog")
    choose(dialog, sup, "New Investigator", "Meena", search="Meena")
    field(dialog, "Reason (kept in the history)").fill("Fictional: SI Arun has moved to another unit; SI Meena takes the case.")
    walk.shot(sup, "34-hand-over")
    dialog.get_by_role("button", name="Hand over", exact=True).click()
    toast(sup, "now leads")
    expect(sup.get_by_text("SI Meena Iyer (fictional)").first).to_be_visible()
    meena.goto(b_url)
    expect(meena.get_by_text("Investigator (case lead)").first).to_be_visible()
    arun.goto(b_url)
    expect(arun.get_by_text("You: Sub Investigator")).to_be_visible()  # the old lead stays, as a Sub Investigator
    walk.step(f"hand-over: the supervisor gave {case_b} to SI Meena; SI Arun stays on it as a Sub Investigator")

    viewer = walk.login(browser, "kh.viewer")
    viewer.goto(a_url)
    expect(viewer.get_by_text("Not found").first).to_be_visible()
    walk.step("access is enforced by the backend: a viewer who isn't on the case gets 'Not found'")

    # The administrator turns on two-step verification, then logs in again with a code.
    admin.goto(f"{walk.url}/kh/account")
    admin.get_by_role("button", name="Turn on").click()
    dialog = admin.get_by_role("dialog")
    secret = dialog.locator("code").first.inner_text().strip()
    dialog.locator("input").first.click()
    admin.keyboard.type(pyotp.TOTP(secret).now())
    dialog.get_by_role("button", name="Turn on").click()
    toast(admin, "Two-step verification is on")
    second = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark").new_page()
    open_pages.append(second)
    second.goto(f"{walk.url}/login")
    field(second, "Username").fill("kh.admin")
    field(second, "Password").fill(PASSWORD)
    second.get_by_role("button", name="Log in").click()
    expect(second.get_by_text("Two-step verification")).to_be_visible()
    walk.shot(second, "33-login-second-step")
    second.locator("input").first.click()
    second.keyboard.type(pyotp.TOTP(secret).at(int(time.time()) + 30))  # the next code: the first one was used to confirm
    second.get_by_role("button", name="Verify and log in").click()
    expect(second.get_by_text("Welcome,")).to_be_visible()
    walk.step("two-step verification: the administrator turned it on and logged in again with a code")

    sup.goto(a_url)
    sup.get_by_role("button", name="Use light mode").click()
    walk.shot(sup, "06b-case-overview-light")


def run(walk: Walk) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            steps(walk, browser)
        except Exception:
            for i, page in enumerate(open_pages):  # a picture of each open page, for finding out why
                try:
                    page.screenshot(path=str(walk.shots / f"FAILED-{i}.png"), full_page=True)
                except Exception:  # nosec B112 - the page may already be closed
                    continue
            raise
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--shots", type=Path, default=Path("walkthrough-screens"))
    args = parser.parse_args()
    started = time.time()
    print(f"Knight Hawk walk-through against {args.url}")
    try:
        run(Walk(args.url, args.shots))
    except Exception as error:  # report which step failed (the pages were pictured as FAILED-n.png), then fail
        print(f"\nFAILED after {len(passed)} steps: {error}")
        sys.exit(1)
    print(f"\nALL {len(passed)} STEPS PASSED in {time.time() - started:.0f} s; screenshots in {args.shots}")


if __name__ == "__main__":
    main()
