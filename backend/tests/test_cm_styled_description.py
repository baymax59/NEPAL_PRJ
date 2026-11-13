"""The styled copy of a case's description (docs/case-management/13-plain-case-design.md, section 12): the formatting the editor offers is
kept, everything else is cleaned out before it is stored, and the plain description stays what reports and search read. All fictional."""

import pytest
from cm_support import CASE, case, create_case

from app.casemgmt import rich_text

PLAIN = "A complainant reports three unauthorised transfers after a fake KYC message."
STYLED = (
    '<p style="text-align: center"><strong>Complaint</strong> <em>received</em> <u>today</u></p>'
    '<ul><li><p><span style="color: #c92a2a">three transfers</span></p></li></ul>'
    '<p><span style="font-family: Georgia; font-size: 18px">Georgia, 18 px</span></p>'
)


def test_the_formatting_the_editor_makes_is_kept():
    kept = rich_text.clean(STYLED)
    for piece in ("<strong>Complaint</strong>", "<em>received</em>", "<u>today</u>", "<ul><li>", "text-align: center", "color: #c92a2a",
                  "font-family: Georgia", "font-size: 18px"):
        assert piece in kept, piece


@pytest.mark.parametrize("attack", [
    '<script>alert(1)</script>Text here',
    '<p onclick="alert(1)">Text here</p>',
    '<img src=x onerror="alert(1)">Text here',
    '<a href="javascript:alert(1)">Text here</a>',
    '<iframe src="https://example.com"></iframe>Text here',
    '<p style="background: url(https://example.com/x.png)">Text here</p>',
    '<span style="color: red; position: fixed; top: 0">Text here</span>',
    '<p style="color: expression(alert(1))">Text here</p>',
    '<style>body{display:none}</style>Text here',
    '<!-- comment -->Text here',
])
def test_anything_unsafe_or_unknown_is_cleaned_out(attack):
    cleaned = rich_text.clean(attack)
    assert "Text here" in cleaned
    for bad in ("script", "onclick", "onerror", "javascript", "iframe", "url(", "expression", "position", "display", "<img", "<a ", "<style", "<!--"):
        assert bad not in cleaned, (bad, cleaned)


def test_nothing_left_to_show_is_stored_as_nothing():
    assert rich_text.clean(None) is None and rich_text.clean("   ") is None
    assert rich_text.clean("<p></p><p><br></p>") is None
    assert rich_text.clean("<script>alert(1)</script>") is None


def test_a_case_keeps_both_copies_and_the_plain_one_stays_plain(cm_client):
    sup = cm_client("sup.styled", "supervisor", "confidential")
    created = create_case(sup, description=PLAIN, description_html=STYLED)
    detail = case(sup, created["case_id"])
    assert detail["description"] == PLAIN  # what reports, search and the assistant read: no tags
    assert "<strong>Complaint</strong>" in detail["description_html"] and "color: #c92a2a" in detail["description_html"]


def test_a_styled_copy_with_a_script_is_cleaned_when_the_case_is_registered(cm_client):
    sup = cm_client("sup.styled2", "supervisor", "confidential")
    created = create_case(sup, description=PLAIN, description_html='<p onmouseover="steal()">Hello <script>steal()</script>there</p>')
    html = case(sup, created["case_id"])["description_html"]
    assert "steal" not in html and "Hello" in html and "there" in html


def test_a_case_without_a_styled_copy_shows_none(cm_client):
    sup = cm_client("sup.styled3", "supervisor", "confidential")
    created = create_case(sup, description=PLAIN)
    detail = case(sup, created["case_id"])
    assert detail["description_html"] is None and detail["description"] == PLAIN


# ---------------------------------------------------------------- who reported the case (design 13, section 12)


def test_a_case_can_record_who_reported_it(cm_client):
    sup = cm_client("sup.reporter", "supervisor", "confidential")
    reporter = {"name": "Meera Nair (fictional)", "phone": "+91 70000 00001", "email": "meera@example.invalid", "address": "12 Example Road"}
    created = create_case(sup, reported_by=reporter)
    assert case(sup, created["case_id"])["reported_by"] == {"unknown": False, **reporter}


def test_the_reporter_is_not_required(cm_client):
    sup = cm_client("sup.reporter2", "supervisor", "confidential")
    created = create_case(sup)  # nothing sent: nothing recorded
    assert case(sup, created["case_id"])["reported_by"] is None
    blank = create_case(sup, reported_by={"name": "  ", "phone": ""})  # blank entries are nothing
    assert case(sup, blank["case_id"])["reported_by"] is None


def test_the_reporter_can_be_unknown(cm_client):
    sup = cm_client("sup.reporter3", "supervisor", "confidential")
    created = create_case(sup, reported_by={"unknown": True})
    assert case(sup, created["case_id"])["reported_by"] == {"unknown": True, "name": None, "phone": None, "email": None, "address": None}


def test_unknown_and_details_do_not_go_together(cm_client):
    sup = cm_client("sup.reporter4", "supervisor", "confidential")
    refused = sup.post("/api/v1/cases", json={**CASE, "reported_by": {"unknown": True, "name": "Someone"}})
    assert refused.status_code == 422 and "unknown" in refused.text.lower()


def test_an_email_that_is_not_an_email_is_refused(cm_client):
    sup = cm_client("sup.reporter5", "supervisor", "confidential")
    refused = sup.post("/api/v1/cases", json={**CASE, "reported_by": {"email": "not an email"}})
    assert refused.status_code == 422
