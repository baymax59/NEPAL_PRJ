"""Finding cited provisions, using citation styles from the real judgments."""

import pytest

from app.explain.provisions import extract_provisions


def labels(text: str) -> list[str]:
    return [p.label for p in extract_provisions(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("convicted under Section 302 IPC", ["Section 302 IPC"]),
        ("Sections 302 and 34 of the Indian Penal Code", ["Section 302 IPC", "Section 34 IPC"]),
        ("powers under Section 482 of the Cr.P.C. are", ["Section 482 CrPC"]),
        ("may file a B Report u/s.173 CrPC – However", ["Section 173 CrPC"]),
        ("challenged the notice under Section 13(2) of the SARFAESI Act", ["Section 13 of the SARFAESI Act"]),
        ("barred by Section 41(h) of the Specific Relief Act, 1963.", ["Section 41 of the Specific Relief Act"]),
        ("Proviso to Section 48-A of the Karnataka Land Reforms Act", ["Section 48A of the Karnataka Land Reforms Act"]),
        ("Section 103 of the Bharatiya Nyaya Sanhita, 2023", ["Section 103 BNS"]),
    ],
)
def test_sections_with_their_act(text, expected):
    assert labels(text) == expected


def test_headnote_style_with_the_act_first():
    text = "Code of Civil Procedure, 1908 – ss.96, 105 & Or.IX, r.13 – Ex-parte decree. Penal Code, 1860 – s.302 – Murder"

    assert labels(text) == ["Section 96 CPC", "Section 105 CPC", "Order IX Rule 13 CPC", "Section 302 IPC"]


def test_sections_read_with_another_section_all_get_the_act():
    # From Boby v. State of Kerala (2023): Section 302 was once missed because of "read with".
    text = "offences punishable under Sections 395, 364, 365, 380 and 302 read with Section 34 of the IPC."

    assert labels(text) == [f"Section {n} IPC" for n in (395, 364, 365, 380, 302, 34)]


def test_headnote_with_an_abbreviation_and_no_year():
    # Also from Boby: "IPC – ss. ..." instead of "Penal Code, 1860 – ss. ...".
    text = "Appellant acquitted – IPC – ss. 395, 364, 302 and 302 r/w s.34. Evidence Act, 1872 – s.27 – A"

    assert labels(text) == [
        "Section 395 IPC",
        "Section 364 IPC",
        "Section 302 IPC",
        "Section 302 IPC",
        "Section 34 IPC",
        "Section 27 of the Evidence Act",
    ]


def test_articles_belong_to_the_constitution_unless_another_document_is_named():
    assert labels("Articles 14 and 21 of the Constitution of India") == [
        "Article 14 of the Constitution",
        "Article 21 of the Constitution",
    ]
    assert labels("a petition under Article 226 was filed") == ["Article 226 of the Constitution"]
    assert labels("Article 6 of the Convention on Human Rights") == []


def test_cpc_orders_and_rules():
    assert labels("rejected under Order VII Rule 11 of the plaint") == ["Order VII Rule 11 CPC"]


def test_different_names_for_the_same_act_give_the_same_provision():
    short = extract_provisions("Section 6A of the DSPE Act")
    full = extract_provisions("Section 6A of the Delhi Special Police Establishment Act, 1946")

    assert short[0].key == full[0].key == "dspe act|section|6A"


@pytest.mark.parametrize(
    "text",
    [
        "Section 4 of the Act",  # which Act? unknown
        "Section 12 of the said Act",
        "an appeal u/s.96 was filed",  # no Act named
        "Section 9 B of the Act",  # once produced the bogus Act "B of the Act"
        "Section 302",
    ],
)
def test_sections_without_a_named_act_are_skipped(text):
    assert labels(text) == []


def test_a_stray_initial_before_the_act_name_is_dropped():
    assert labels("Kaul, J. Securities and Exchange Board of India Act, 1992 – s.11") == ["Section 11 of the SEBI Act"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Offences: BNS 318(4), 316(2), 61(2)", ["Section 318 BNS", "Section 316 BNS", "Section 61 BNS"]),
        ("registered under IPC 420/406/120B", ["Section 420 IPC", "Section 406 IPC", "Section 120B IPC"]),
        ("notice under BNSS 35 was served", ["Section 35 BNSS"]),
        ("Offence registered: BNS 303(2) (theft).", ["Section 303 BNS"]),
    ],
)
def test_fir_register_style_with_the_act_first(text, expected):
    assert labels(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "the IPC 1860 and the CrPC 1973 apply",  # years, not sections
        "the Indian Penal Code, 1860",
        "the SEBI Act 15 times",  # only the criminal codes are read this way
        "NIPC 420",  # not an Act abbreviation at all
    ],
)
def test_act_first_style_ignores_years_and_other_acts(text):
    assert labels(text) == []
