"""Browser run of the final acceptance scenario (spec §27), on the plain case design: the 17 steps in order, each done on screen by
the person the spec names, with the demonstration's fictional evidence (backend/scripts/demo/files.py). Each step is the plain-case
equivalent of the spec's git-style step (docs/case-management/10-acceptance-and-traceability.md).

It also proves that pages are live: they update by themselves, without reloading, while other people work
(the investigator's file list when the Sub Investigator adds an exhibit, the Sub Investigator's case page when the supervisor
approves, the administrator's history of the case when the investigator corrects a note).

1. Prepare the throwaway database (only ever casesdb_e2e):      cd backend;  uv run python -m scripts.e2e_prepare
2. Start the API on it, and the web app pointing at that API (see docs/steps/15-4-screens.md).
3. Run (from backend/, whose Python has a working Playwright):
       uv run --with playwright python ../frontend/e2e/acceptance.py --url http://127.0.0.1:5180 --shots <folder>

All people, cases and evidence are FICTIONAL. Exit code 0 only if all 17 steps passed.
"""

import argparse
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Browser, Page, expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))  # the demonstration's fictional evidence
from scripts.demo import files as demo  # noqa: E402
from walkthrough import TOKEN_KEY, Walk, change_status, choose, field, open_pages, passed, registered_case_id, tab, toast, write_description  # noqa: E402

TITLE = "Online Banking Fraud Investigation (FICTIONAL)"
LIVE = 45_000  # how long a page may take to update by itself (the stream checks every 5 s; admin pages every 15 s)
SPEC = {
    1: "An administrator registers Case A",
    2: "The system permanently makes the case's folders and its first history entry",
    3: "Investigator 1 is the case's lead and finds it among his cases",
    4: "Investigator 1 uploads evidence and writes investigation notes",
    5: "Investigator 1 adds a folder for the telecom requisitions",
    6: "Investigator 1 adds Investigator 2 (Sub Investigator) and an Analyst to the team, straight in",
    7: "Investigator 2 and the Analyst add their findings straight into the case",
    8: "The supervisor approves the findings",
    9: "The approval is a numbered, tamper-evident entry of the case's history",
    10: "Investigator 1 discovers an incorrect earlier analytical assumption",
    11: "Investigator 1 corrects the note with a new version, saying why",
    12: "The case goes on with the corrected note as the current one",
    13: "The wrong version remains preserved and unchanged",
    14: "The administrator can see every file and version, the team, every history entry and the access history",
    15: "Evidence integrity checks succeed",
    16: "An attempted deletion or destructive history rewrite is rejected and audited",
    17: "The system generates a case report with provenance and integrity information",
}
FETCH_STATUS = """async ([method, url, key]) => (await fetch(url, {method, headers: {Authorization: 'Bearer ' + sessionStorage.getItem(key)}})).status"""


def done(walk: Walk, step: int, detail: str = "") -> None:
    walk.step(f"{step:>2}. {SPEC[step]}{f' ({detail})' if detail else ''}")


def add_evidence(page: Page, url: str, f: demo.DemoFile) -> None:
    page.goto(f"{url}/files")
    page.get_by_role("button", name="Add exhibit").first.click()
    dialog = page.get_by_role("dialog")
    dialog.locator('input[type="file"]').set_input_files(files=[{"name": f.name, "mimeType": f.mime, "buffer": f.content}])
    choose(dialog, page, "Folder", f.folder)  # the case type's folder (e.g. cdr-analysis)
    field(dialog, "Title").fill(f.title)
    field(dialog, "Source").fill(f.source)
    dialog.get_by_role("button", name="Add to the case").click()
    toast(page, "added to the case")


def add_note(page: Page, url: str, title: str, text: str, folder: str, kind: str | None = None) -> None:
    page.goto(f"{url}/files")
    page.get_by_role("button", name="New note").first.click()
    dialog = page.get_by_role("dialog")
    choose(dialog, page, "Folder", folder)
    if kind:
        choose(dialog, page, "Kind", kind)
    field(dialog, "Title").fill(title)
    field(dialog, "Text").fill(text)
    dialog.get_by_role("button", name="Add to the case").click()
    toast(page, "Added to the case")


def steps(walk: Walk, browser: Browser) -> None:
    files = demo.evidence()

    # 1. An administrator registers Case A, with Inspector Arun as the assigned investigator.
    admin = walk.login(browser, "kh.admin")
    admin.get_by_role("link", name="Register a case").first.click()
    field(admin, "Title").fill(TITLE)
    choose(admin, admin, "Type of case", "Cyber / online fraud")
    write_description(admin, "FICTIONAL demonstration. Reported loss: INR 2,50,000 (INR 250000) in three UPI transfers "
                             "after a 'KYC update' WhatsApp message and a new-device login.")
    choose(admin, admin, "Lead investigator", "SI Arun Kumar", search="Arun")
    choose(admin, admin, "Supervisor (recommended)", "Devika", search="Devika")
    field(admin, "Number").fill("0117/2026")
    walk.shot(admin, "01-administrator-registers-case-a")
    admin.get_by_role("button", name="Register the case").click()
    expect(admin.get_by_text("Case registered", exact=True).first).to_be_visible()
    case = re.search(r"[A-Z]{2,10}-\d{4}-\d{4}", admin.locator("h2").first.inner_text()).group(0)
    case_id = registered_case_id(admin)
    url = f"{walk.url}/kh/case/{case_id}"
    done(walk, 1, f"{case}, by the administrator")

    # 2. Its folders (from the type of case) and its first history entry exist from the start; the history checks out.
    expect(admin.get_by_text("10 folders made for you")).to_be_visible()
    walk.shot(admin, "02-folders-made-at-registration")
    admin.goto(url)
    for folder in ("case-information", "complainant", "digital-evidence", "cdr-analysis", "ipdr-analysis", "investigation-notes"):
        expect(admin.get_by_role("link", name=folder, exact=True)).to_be_visible()
    tab(admin, "History")
    expect(admin.get_by_text("Case registered").first).to_be_visible()
    admin.get_by_role("button", name="Check the history").click()
    expect(admin.get_by_text("History is intact")).to_be_visible()
    done(walk, 2, "ten folders, history entry 1, 'History is intact'")

    # 3. Investigator 1 is the case's lead: it is among his cases, with that part.
    arun = walk.login(browser, "kh.arun")
    expect(arun.get_by_role("link", name=TITLE).first).to_be_visible()
    expect(arun.get_by_text("Investigator (case lead)").first).to_be_visible()
    arun.get_by_role("link", name=TITLE).first.click()
    expect(arun.get_by_text("You: Investigator (case lead)")).to_be_visible()
    walk.shot(arun, "03-investigator-leads-the-case")
    done(walk, 3, f"{case} among Inspector Arun's cases, as lead")

    # 4. Investigator 1 uploads evidence and writes investigation notes.
    add_note(arun, url, "Complaint summary (fictional)", demo.COMPLAINT_SUMMARY, folder="complainant")
    add_evidence(arun, url, files["whatsapp"])
    add_evidence(arun, url, files["statement"])
    add_evidence(arun, url, files["access_log"])
    arun.goto(f"{url}/history")
    expect(arun.get_by_text("Exhibit added").first).to_be_visible()
    walk.shot(arun, "04-evidence-and-notes")
    done(walk, 4, "3 exhibits and a note, each a numbered entry of the history")

    # 5. Investigator 1 adds a folder of his own for the telecom requisitions.
    arun.goto(f"{url}/files")
    arun.get_by_role("button", name="New folder").click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Folder name").fill("telecom-requisitions")
    dialog.get_by_role("button", name="Add folder").click()
    toast(arun, "Folder telecom-requisitions added")
    done(walk, 5, "telecom-requisitions")

    # 6. Investigator 1 adds Investigator 2 as a Sub Investigator and an Analyst: straight in, no invitation, no approval.
    tab(arun, "Team")
    arun.get_by_role("button", name="Add team member").click()
    dialog = arun.get_by_role("dialog")
    choose(dialog, arun, "Colleague", "Meena", search="Meena")
    dialog.get_by_role("button", name="Add to the team").click()
    toast(arun, "is now on the team")
    arun.get_by_role("button", name="Add team member").click()
    dialog = arun.get_by_role("dialog")
    choose(dialog, arun, "Colleague", "Dev", search="Dev")
    choose(dialog, arun, "Part in the case", "Analyst")
    dialog.get_by_role("button", name="Add to the team").click()
    toast(arun, "is now on the team")
    walk.shot(arun, "06-team-added-straight-in")
    meena = walk.login(browser, "kh.meena")
    expect(meena.get_by_role("link", name=TITLE).first).to_be_visible()  # no invitation to accept: it is already among her cases
    expect(meena.get_by_text("Sub Investigator").first).to_be_visible()
    dev = walk.login(browser, "kh.dev")
    expect(dev.get_by_role("link", name=TITLE).first).to_be_visible()
    expect(dev.get_by_text("Analyst").first).to_be_visible()
    done(walk, 6, "SI Meena (Sub Investigator) and Dev (Analyst) are on the team at once")

    # 7. Investigator 2 and the Analyst add their findings. Meanwhile Inspector Arun's file list stays open: it updates live.
    arun.goto(f"{url}/files")
    expect(arun.get_by_text("Complaint summary (fictional)").first).to_be_visible()
    add_evidence(meena, url, files["cdr"])
    expect(arun.get_by_text(files["cdr"].title).first).to_be_visible(timeout=LIVE)  # no reload on Arun's side
    walk.shot(arun, "07a-live-file-list-updated")
    walk.step("   live: Inspector Arun's open file list showed SI Meena's new exhibit without reloading")
    add_evidence(meena, url, files["ipdr"])
    add_note(meena, url, "CDR and IPDR findings (fictional)", demo.CDR_FINDINGS, folder="cdr-analysis")
    add_note(dev, url, "Pattern of the three debits (fictional)", "Three debits within six minutes to one payee: the pattern of a mule account (fictional).",
             folder="investigation-notes", kind="Analysis")
    expect(dev.get_by_role("button", name="Add team member")).to_have_count(0)  # an Analyst adds files, not people
    walk.shot(meena, "07b-findings-added")
    done(walk, 7, "SI Meena added the CDR, the IPDR and her findings; the Analyst an analysis: all in the case at once")

    # 8. The supervisor approves the findings. SI Meena's case page stays open: it updates live.
    sup = walk.login(browser, "kh.supervisor")
    arun.goto(url)
    change_status(arun, "Under investigation", "Investigation under way (fictional)")
    change_status(arun, "Pending review", "The findings are in: ready for the supervisor's review (fictional)")
    meena.goto(url)
    expect(meena.get_by_text("Pending review").first).to_be_visible()
    sup.goto(url)
    expect(sup.get_by_text("You oversee this case")).to_be_visible()
    change_status(sup, "Approved for reporting", "Checked against the exhibits. Approved (fictional).")
    expect(meena.get_by_text("Approved for reporting").first).to_be_visible(timeout=LIVE)
    walk.step("   live: SI Meena's open case page showed the supervisor's approval without reloading")
    done(walk, 8, "approved for reporting, with a reason")

    # 9. The approval is a numbered entry of the history, by the supervisor; the history still checks out.
    arun.goto(f"{url}/history")
    expect(arun.get_by_text(re.compile("approved for reporting", re.IGNORECASE)).first).to_be_visible()
    arun.get_by_role("button", name="Check the history").click()
    expect(arun.get_by_text("History is intact")).to_be_visible()
    walk.shot(arun, "09-approval-in-the-history")
    done(walk, 9, "the approval is an entry of the history, in order; 'History is intact'")

    # 10. Investigator 1 writes an attribution resting on a wrong assumption, then records its discovery as a comment on it.
    add_note(arun, url, "Attribution of the login (fictional)", demo.WRONG_ATTRIBUTION, folder="investigation-notes")
    arun.goto(f"{url}/files?folder=investigation-notes")
    arun.get_by_text("Attribution of the login (fictional)", exact=True).first.click()
    arun.get_by_label("Comment").fill(demo.DISCOVERY)
    arun.get_by_role("button", name="Comment", exact=True).click()
    expect(arun.get_by_text(re.compile("INCORRECT ASSUMPTION FOUND")).first).to_be_visible()
    walk.shot(arun, "10-incorrect-assumption-discovered")
    done(walk, 10, "the UTC time read as IST; the discovery is a comment on that note")

    # 11. Investigator 1 corrects the note with a new version, saying why.
    #     The administrator's page of the case is open meanwhile: the correction appears in its history by itself.
    admin.goto(f"{walk.url}/kh/admin/cases/{case_id}")
    expect(admin.get_by_text("Note added").first).to_be_visible()
    expect(admin.get_by_text("New version")).to_have_count(0)
    arun.get_by_role("button", name="New version").click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Text").fill(demo.corrected_attribution("NOTE"))
    field(dialog, "What changed").fill("The bank's access log is in UTC, not IST: the subscriber named in version 1 held the address five hours earlier (fictional)")
    walk.shot(arun, "11-correct-with-a-new-version")
    dialog.get_by_role("button", name="Save new version").click()
    toast(arun, "Saved as a new version")
    expect(arun.get_by_text("version 2 of 2")).to_be_visible()
    done(walk, 11, "version 2, with the reason")
    expect(admin.get_by_text("New version").first).to_be_visible(timeout=LIVE)
    walk.step("   live: the administrator's open page of the case showed the correction in its history without reloading")

    # 12. The case goes on with the corrected note as its current one: more work follows.
    arun.keyboard.press("Escape")
    arun.goto(f"{url}/files?folder=investigation-notes")
    expect(arun.get_by_text("version 2").first).to_be_visible()
    arun.goto(f"{walk.url}/kh/cases")
    expect(arun.get_by_role("link", name=TITLE).first).to_be_visible()
    walk.shot(arun, "12-the-case-goes-on")
    done(walk, 12, "the corrected note is version 2 and the case goes on")

    # 13. The wrong version remains preserved and unchanged: both versions are in the note, and the history is intact.
    admin.goto(f"{url}/files?folder=investigation-notes")
    admin.get_by_text("Attribution of the login (fictional)", exact=True).first.click()
    expect(admin.get_by_text("version 2 of 2")).to_be_visible()
    expect(admin.get_by_text(demo.OTHER_PHONE).first).to_be_visible()  # the wrong attribution, kept in version 1 (shown as what changed)
    expect(admin.get_by_text("First version.")).to_be_visible()
    walk.shot(admin, "13-version-1-preserved")
    admin.goto(f"{url}/history")
    admin.get_by_role("button", name="Check the history").click()
    expect(admin.get_by_text("History is intact")).to_be_visible()
    done(walk, 13, "version 1 kept with the error as its record; 'History is intact'")

    # 14. The administrator sees every file and version, the team, every history entry and the access history.
    admin.goto(f"{walk.url}/kh/admin/cases/{case_id}")
    expect(admin.get_by_text("Case registered").first).to_be_visible()
    expect(admin.get_by_text("New version").first).to_be_visible()
    walk.shot(admin, "14a-admin-history")
    admin.get_by_role("tab", name="Access history").click()
    expect(admin.get_by_text(re.compile("Meena")).first).to_be_visible()
    expect(admin.get_by_text("became Analyst").first).to_be_visible()
    walk.shot(admin, "14b-admin-access-history")
    admin.get_by_role("tab", name="Audit trail").click()
    expect(admin.get_by_text("cm.case.status_changed").first).to_be_visible()  # the newest events come first (older ones: "Older events")
    admin.goto(f"{url}/team")
    expect(admin.get_by_text("Dev Patel (fictional)").first).to_be_visible()
    done(walk, 14, "the history, the access history, the team and the audit trail")

    # 15. Evidence integrity checks succeed.
    exhibits = 0
    for f in (files["whatsapp"], files["access_log"], files["cdr"]):
        arun.goto(f"{url}/files?folder={f.folder}")
        arun.get_by_text(f.title, exact=True).first.click()
        arun.get_by_role("link", name=re.compile("Open the exhibit")).click()
        arun.get_by_role("button", name="Verify integrity now").click()
        expect(arun.get_by_text("File is original").first).to_be_visible()
        exhibits += 1
    walk.shot(arun, "15-integrity-verified")
    done(walk, 15, f"{exhibits} exhibits re-hashed: File is original")

    # 16. Attempted deletion and history rewrite: refused (405) and audited.
    deleted = arun.evaluate(FETCH_STATUS, ["DELETE", f"/api/v1/cases/{case_id}", TOKEN_KEY])
    rewrite = arun.evaluate(FETCH_STATUS, ["PATCH", f"/api/v1/cases/{case_id}/history/2", TOKEN_KEY])
    if (deleted, rewrite) != (405, 405):
        raise RuntimeError(f"deletion answered {deleted}, rewrite answered {rewrite}")
    admin.goto(f"{walk.url}/kh/admin/cases/{case_id}")
    admin.get_by_role("tab", name="Audit trail").click()
    admin.get_by_text("Refused and denied", exact=True).click()
    expect(admin.get_by_text("cm.destructive_operation.rejected").first).to_be_visible()
    walk.shot(admin, "16-deletion-refused-and-audited")
    done(walk, 16, "DELETE and a history rewrite answered 405, both in the audit trail")

    # 17. A signed case report with provenance and integrity information, downloaded and checked.
    arun.goto(f"{url}/reports")
    expect(arun.get_by_text(re.compile("not automatically admissible")).first).to_be_visible()
    arun.get_by_role("button", name="Generate a signed PDF").click()
    dialog = arun.get_by_role("dialog")
    field(dialog, "Purpose").fill("Supervisor's review of the corrected attribution (FICTIONAL DEMONSTRATION)")
    dialog.get_by_role("button", name="Generate", exact=True).click()
    toast(arun, re.compile(r"RPT-0001 version 1 generated, as of entry \d+"))
    with arun.expect_download() as downloaded:
        arun.get_by_role("button", name="Download RPT-0001 version 1").click()
    report_file = walk.shots / "acceptance-RPT-0001-v1.pdf"
    downloaded.value.save_as(report_file)
    arun.goto(f"{walk.url}/kh/verify-report")
    arun.locator('input[type="file"]').set_input_files(str(report_file))
    arun.get_by_role("button", name="Check", exact=True).click()
    expect(arun.get_by_text("Genuine: exactly the report Knight Hawk generated")).to_be_visible()
    expect(arun.get_by_text(re.compile(r"the case as of Entry \d+"))).to_be_visible()
    walk.shot(arun, "17-report-genuine")
    done(walk, 17, "RPT-0001 version 1, downloaded and checked: genuine")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:5180")
    parser.add_argument("--shots", type=Path, default=Path("acceptance-screens"))
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")  # the Windows console can't print every character of a page
    started = time.time()
    walk = Walk(args.url, args.shots)
    print(f"Knight Hawk final acceptance scenario (spec section 27) in the browser, against {args.url}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            steps(walk, browser)
        except Exception as error:
            for i, page in enumerate(open_pages):
                try:
                    page.screenshot(path=str(args.shots / f"FAILED-{i}.png"), full_page=True)
                except Exception:  # nosec B112 - the page may already be closed
                    continue
            print(f"\nFAILED after {len(passed)} lines: {error}")
            sys.exit(1)
        finally:
            browser.close()
    numbered = [p for p in passed if p[:2].strip().isdigit()]
    print(f"\nALL {len(numbered)} ACCEPTANCE STEPS PASSED (and {len(passed) - len(numbered)} live-page checks) "
          f"in {time.time() - started:.0f} s; screenshots in {args.shots}")
    if len(numbered) != 17:
        sys.exit(1)


if __name__ == "__main__":
    main()
