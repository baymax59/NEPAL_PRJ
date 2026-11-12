"""Page cleaning, using patterns seen in the real Supreme Court Reports PDFs."""

from app.documents.clean import clean_pages

MARGIN = "A\nB\nC\nD\nE\nF\nG\nH\n"
# Real page bodies differ in their words, not just their numbers.
TOPICS = ["limitation", "jurisdiction", "evidence", "costs", "remand", "decree", "appeal", "notice"]


def body(i: int) -> str:
    return f"Body text discussing {TOPICS[i]} under Order IX of the Code."


def scr_pages(count: int) -> list[str]:
    """Pages laid out like the SCR PDFs: margin letters, running headers on alternating pages."""
    pages = []
    for i in range(count):
        number = 203 + i
        text = body(i)
        if i % 2:  # even page numbers: header at the top
            pages.append(f"{MARGIN}{number} SUPREME COURT REPORTS [2022] 11 S.C.R.\r\n{text}\r\n")
        else:  # odd page numbers: number at the top, case title and judge at the bottom
            pages.append(
                f"{MARGIN}{number}\r\n{text}\r\nG.N.R. BABU @ S.N. BABU v. DR. B.C. MUTHAPPA & ORS.\r\n"
                "[ABHAY S. OKA, J.]\r\n"
            )
    return pages


def test_pdfium_special_characters_are_fixed():
    [page] = clean_pages(["a tax￾payer and decision￾making\n Ramesh Gobindram v. Sugra"])

    assert page == "a tax-payer and decision-making • Ramesh Gobindram v. Sugra"


def test_margin_letters_and_page_numbers_are_removed():
    [page] = clean_pages([f"{MARGIN}205\r\nThe appeal is allowed.\r\n"])

    assert page == "The appeal is allowed."


def test_running_headers_and_footers_are_removed_but_body_text_is_kept():
    cleaned = clean_pages(scr_pages(8))

    assert cleaned == [body(i) for i in range(8)]


def test_header_merged_with_another_line_on_the_first_page_is_removed():
    # Layout of a real 4-page judgment (2022_3_362_365): pdfium joins the page-1 header and
    # footer into one line, so the plain header appears only once more, on page 3.
    # The page-1 party line is also the start of the running title at the bottom of pages 2
    # and 4; it must survive (an earlier version of the cleaner removed it).
    running_title = "SHRI M.L. PATIL (DEAD) THROUGH LRS v. THE STATE OF\nGOA AND ANR."
    pages = [
        "362 SUPREME COURT REPORTS [2022] 3 S.C.R. [2022] 3 S.C.R. 362\nSHRI M.L. PATIL (DEAD) THROUGH LRS\nv.\n"
        "THE STATE OF GOA AND ANR.\nService Law: Pension.",
        f"Second page one.\nSecond page two.\nSecond page three.\nSecond page four.\n{running_title}",
        "364 SUPREME COURT REPORTS [2022] 3 S.C.R.\nThird page one.\nThird page two.\nThird page three.",
        f"Fourth page one.\nFourth page two.\nFourth page three.\nFourth page four.\n{running_title}",
    ]

    cleaned = clean_pages(pages)

    assert cleaned[0] == "SHRI M.L. PATIL (DEAD) THROUGH LRS v. THE STATE OF GOA AND ANR. Service Law: Pension."
    assert cleaned[1] == "Second page one. Second page two. Second page three. Second page four."
    assert cleaned[2] == "Third page one. Third page two. Third page three."
    assert cleaned[3] == "Fourth page one. Fourth page two. Fourth page three. Fourth page four."


def test_short_repeated_fragments_do_not_remove_sentences_that_start_with_them():
    pages = [f"v.\nv. the respondent argued point {TOPICS[i]} at length.\nMore text {TOPICS[i]}." for i in range(6)]

    assert all(page.startswith("v. the respondent argued") for page in clean_pages(pages))


def test_words_split_after_ligatures_are_rejoined():
    # Real examples from the judgments: a space after the fi/ff ligature glyph.
    [page] = clean_pages(["The off ence was fi led before the Offi cer, to whose eff ect the diff erent views apply."])

    assert page == "The offence was filed before the Officer, to whose effect the different views apply."


def test_real_word_pairs_next_to_ligatures_stay_apart():
    pages = [
        "The plaintiff has filed a suit. The plaintiff therein relied on the cut off date. "
        "Rafi said he saw it.",
        "The date was fixed. It has been argued therein. The plaintiff, and Rafi, appeared.",
    ]

    cleaned = clean_pages(pages)

    assert "plaintiff has" in cleaned[0]
    assert "plaintiff therein" in cleaned[0]
    assert "cut off date" in cleaned[0]
    assert "Rafi said" in cleaned[0]


def test_a_line_that_appears_only_once_is_kept():
    pages = scr_pages(6)
    pages[0] += "[2022] 11 S.C.R. 203\r\n"  # first-page footer, appears once

    assert clean_pages(pages)[0].endswith("[2022] 11 S.C.R. 203")


def test_short_documents_are_not_checked_for_repetition():
    pages = ["JUDGMENT\nFirst page text.", "JUDGMENT\nSecond page text.", "JUDGMENT\nThird page text."]

    assert clean_pages(pages)[0] == "JUDGMENT First page text."


def test_repeated_text_in_the_middle_of_a_page_is_kept():
    pages = [f"Top {i}\nline one\nline two\nline three\nThe court held:\nline four\nline five\nline six\nBottom {i}"
             for i in range(6)]

    assert all("The court held:" in page for page in clean_pages(pages))


def test_broken_lines_are_joined_and_numbered_paragraphs_start_on_a_new_line():
    [page] = clean_pages(["a multi-\nstoreyed building was\nconstructed.\n12. In our view, the decree\nis illegal."])

    assert page == "a multi-storeyed building was constructed.\n12. In our view, the decree is illegal."
