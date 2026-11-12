"""Build a case timeline from the judgment text, each event tied to its page.

Three kinds of event, each labelled with how it was obtained:
- "judgment": the decision date and recorded outcome, from the source's metadata fields.
- "order_under_appeal": from the header line "From the Judgment and Order dated 10.01.2022 of
  the High Court of Chhattisgarh at Bilaspur in ...".
- "dated_mention": any other date in the text, with the sentence around it.

Dates are only kept between 1900 and the decision date. Sentences that cite other judgments
("(2005) 1 SCC 787", "AIR 1952 SC 1", "supra", "decided on") are skipped: those dates belong to
earlier cases, not this one. All of this is automatic and labelled for checking against the page.
"""

import datetime as dt
import re
from dataclasses import dataclass

from app.extraction.courts import canonical_court
from app.extraction.dates import find_dates, sentence_around

MIN_DATE = dt.date(1900, 1, 1)
MAX_MENTIONS = 40  # per document; the earliest in the text are kept (facts usually come first)

ORDER_UNDER_APPEAL = re.compile(
    r"From the (?:final |impugned )?(?:Judgments?|Orders?)(?: and (?:final )?Orders?)? dated (?P<date>.{6,25}?) "
    r"(?:passed )?(?:of|by) the (?P<court>.{5,160}?) in (?=[A-Z0-9(]|the )"
)
CITES_ANOTHER_CASE = re.compile(r"\bSCC\b|\bAIR\s+\d{4}|\(supra\)|\bdecided on\b|\breported in\b|\bS\.C\.R\.\s*\d", re.IGNORECASE)


@dataclass
class Event:
    event_type: str  # "judgment", "order_under_appeal", "dated_mention"
    event_date: dt.date
    date_text: str | None
    description: str
    page_number: int | None
    source_excerpt: str | None
    extraction_method: str  # "source_field" or "rule_based"


def judgment_event(decision_date: dt.date | None, outcome: str | None, court: str | None) -> Event | None:
    if decision_date is None:
        return None
    by = f" by the {court}" if court else ""
    result = f"; recorded outcome: {outcome}" if outcome else "; no outcome recorded in the source"
    return Event(
        "judgment",
        decision_date,
        None,
        f"Judgment delivered{by}{result}",
        None,
        "From the source record's decision date and outcome fields",
        "source_field",
    )


def events_from_pages(pages: list[tuple[int | None, str]], decision_date: dt.date | None) -> list[Event]:
    latest = decision_date or dt.date.today()
    events: list[Event] = []
    seen_dates: set[dt.date] = {decision_date} if decision_date else set()

    for page_number, text in pages:
        for m in ORDER_UNDER_APPEAL.finditer(text):
            dates = find_dates(m.group("date"))
            court = canonical_court(m.group("court"))
            if not dates or not (MIN_DATE <= dates[0].value <= latest):
                continue
            seen_dates.add(dates[0].value)
            events.append(
                Event(
                    "order_under_appeal",
                    dates[0].value,
                    dates[0].text,
                    f"Judgment/order under appeal{f' passed by the {court}' if court else ''}",
                    page_number,
                    " ".join(m.group(0).split()),
                    "rule_based",
                )
            )

    mentions = 0
    for page_number, text in pages:
        for found in find_dates(text):
            if mentions >= MAX_MENTIONS:
                break
            if found.value in seen_dates or not (MIN_DATE <= found.value <= latest):
                continue
            sentence = sentence_around(text, found.start, found.end)
            if CITES_ANOTHER_CASE.search(sentence):
                continue
            seen_dates.add(found.value)
            mentions += 1
            events.append(
                Event("dated_mention", found.value, found.text, sentence, page_number, sentence, "rule_based")
            )
    return sorted(events, key=lambda e: (e.event_date, e.event_type != "order_under_appeal"))
