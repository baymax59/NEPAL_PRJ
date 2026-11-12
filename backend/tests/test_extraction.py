"""Dates, courts and timeline events, using sentences from the real judgments."""

import datetime as dt

import pytest

from app.extraction.courts import find_courts
from app.extraction.dates import find_dates, sentence_around
from app.extraction.timeline import events_from_pages, judgment_event


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("published on 25.12.2012, one candidate", dt.date(2012, 12, 25)),
        ("order dated 17-3-2018 and which", dt.date(2018, 3, 17)),
        ("by an order dated 15th May 2018 with", dt.date(2018, 5, 15)),
        ("decided on 4th May, 1994.", dt.date(1994, 5, 4)),
        ("made on 29 October 2008, before", dt.date(2008, 10, 29)),
        ("(Civil Appeal No. 1548 of 2023) April 11, 2023 [ABHAY S. OKA", dt.date(2023, 4, 11)),
        ("(Criminal Appeal Nos.598-600 of 2013) FEBRUARY 15, 2023 [B. R. GAVAI", dt.date(2023, 2, 15)),
    ],
)
def test_date_formats_used_in_the_judgments(text, expected):
    assert [d.value for d in find_dates(text)] == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "Circular No. 89/7/2006 dated",  # not a date: day 89
        "assessment order was passed on 20.03.20",  # two-digit year: the century would be a guess
        "8.1.10 That the answering respondent",  # paragraph number
        "on 31.02.2019",  # no such day
    ],
)
def test_things_that_are_not_full_dates_are_ignored(text):
    assert find_dates(text) == []


def test_the_sentence_around_a_date_ignores_abbreviations():
    text = "The appeal was heard. Respondent No. 2 filed a complaint u/s 156(3) Cr.P.C on 06.06.2012, which failed. Next."
    [found] = find_dates(text)

    assert sentence_around(text, found.start, found.end) == (
        "Respondent No. 2 filed a complaint u/s 156(3) Cr.P.C on 06.06.2012, which failed."
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the Bombay High Court held", ["High Court of Bombay"]),
        ("the High Court of Judicature at Bombay held", ["High Court of Bombay"]),
        ("High Court of Madhya Pradesh Bench at Indore", ["High Court of Madhya Pradesh"]),
        ("High Court of Punjab & Haryana", ["High Court of Punjab and Haryana"]),
        ("High Court of Jammu and Kashmir and Ladakh", ["High Court of Jammu and Kashmir and Ladakh"]),
        # Real errors found in the 100 judgments, now fixed:
        ("both the High Court of Delhi and Calcutta High Court", ["High Court of Delhi", "High Court of Calcutta"]),
        ("the High Court of Delhi and High Court of Bombay", ["High Court of Delhi", "High Court of Bombay"]),
        ("appeal to The Tribunal was dismissed", []),
        ("the High Court of Kerela", ["High Court of Kerala"]),
        ("Customs, Excise and Service Tax Appellate Tribunal", ["Customs, Excise and Service Tax Appellate Tribunal"]),
        ("The High Court and the Tribunal both erred", []),  # generic: names no court
        ("the Armed Forces Tribunal and the Land Tribunal", ["Armed Forces Tribunal", "Land Tribunal"]),
    ],
)
def test_courts_get_one_name_each(text, expected):
    assert [c.name for c in find_courts(text)] == expected


PAGES = [
    (
        1,
        "CRIMINAL APPELLATE JURISDICTION: Criminal Appeal No. 634 of 2023. From the Judgment and Order dated "
        "10.01.2022 of the High Court of Chhattisgarh at Bilaspur in CRA No. 1 of 2020. The facts follow.",
    ),
    (
        2,
        "The FIR was registered on 05.03.2018. The accused was arrested on 7th March, 2018. "
        "This Court in Sharad Birdhichand Sarda (1984) 4 SCC 116 decided on 17.07.1984 laid down the test. "
        "A letter dated 01.01.2030 was relied upon.",
    ),
]


def test_timeline_has_the_order_under_appeal_and_dated_events_with_pages():
    events = events_from_pages(PAGES, decision_date=dt.date(2023, 1, 12))
    by_date = {e.event_date: e for e in events}

    order = by_date[dt.date(2022, 1, 10)]
    assert order.event_type == "order_under_appeal"
    assert order.description == "Judgment/order under appeal passed by the High Court of Chhattisgarh"
    assert order.page_number == 1
    fir = by_date[dt.date(2018, 3, 5)]
    assert (fir.event_type, fir.page_number, fir.description) == ("dated_mention", 2, "The FIR was registered on 05.03.2018.")
    assert dt.date(2018, 3, 7) in by_date
    assert dt.date(1984, 7, 17) not in by_date  # the date of a cited earlier case
    assert dt.date(2030, 1, 1) not in by_date  # after the decision: impossible
    assert [e.event_date for e in events] == sorted(e.event_date for e in events)


def test_the_judgment_event_comes_from_the_source_record():
    event = judgment_event(dt.date(2023, 1, 12), "Appeal(s) allowed", "Supreme Court of India")

    assert event.extraction_method == "source_field"
    assert event.description == "Judgment delivered by the Supreme Court of India; recorded outcome: Appeal(s) allowed"
    assert judgment_event(None, "Dismissed", None) is None
    assert "no outcome recorded" in judgment_event(dt.date(2023, 1, 1), None, None).description
