"""Find the courts and tribunals a judgment names, under one name each.

"Bombay High Court", "High Court of Bombay" and "High Court of Judicature at Bombay" are all
"High Court of Bombay". Generic phrases ("the High Court", "the Tribunal") are skipped: they
don't say which court.
"""

import re
from dataclasses import dataclass

# Capitalised words, joined by "and"/"&" for names like "Punjab and Haryana" - but never running
# on into the next court ("High Court of Delhi and Calcutta High Court" is two courts).
_NOT_IN_NAME = r"(?!(?:High|Court|Courts|Supreme|Tribunal)\b)"
_PLACE = rf"[A-Z][a-z]+(?:(?:\s+(?:and|&)\s+|\s+){_NOT_IN_NAME}[A-Z][a-z]+)*"
_NOT_A_PLACE = {
    "the", "this", "that", "said", "same", "learned", "hon'ble", "division", "single", "respective",
    "concerned", "jurisdictional", "impugned", "a", "an", "such", "any", "each", "both", "full",
}
# Capitalised function words that can start a phrase but never a court's name ("To The Tribunal").
_LEADING_JUNK = {"to", "the", "by", "before", "from", "of", "and", "in", "on", "with", "at", "for"}

HIGH_COURT_OF = re.compile(rf"\bHigh Court of (?:Judicature (?:at|for) )?(?P<place>{_PLACE})")
PLACE_HIGH_COURT = re.compile(r"\b(?P<place>[A-Z][a-z]+(?: [A-Z][a-z]+)?) High Court\b")
TRIBUNAL = re.compile(r"\b(?P<name>(?:[A-Z][a-z]+ ){1,6}(?:Appellate )?Tribunal)\b")
# "Bench" and similar words end the court's name: "High Court of Madhya Pradesh Bench at Indore".
_NAME_ENDS = re.compile(r"\s+(?:Bench|At|In|On|Dated|Principal|Circuit|Regional)\b.*$")

# Spelling variants and names cut short by a comma ("Customs, Excise and Service Tax ...").
_ALIASES = {
    "Kerela": "Kerala",
    "Service Tax Appellate Tribunal": "Customs, Excise and Service Tax Appellate Tribunal",
    "Excise Service Tax Appellate Tribunal": "Customs, Excise and Service Tax Appellate Tribunal",
    "Custom Excise Service Tax Appellate Tribunal": "Customs, Excise and Service Tax Appellate Tribunal",
}


@dataclass(frozen=True)
class CourtMention:
    name: str
    start: int
    end: int


def _clean_place(place: str) -> str | None:
    place = _NAME_ENDS.sub("", place).replace("&", "and").strip()
    if not place or place.split()[0].lower() in _NOT_A_PLACE:
        return None
    return _ALIASES.get(place, place)


def _clean_tribunal(name: str) -> str | None:
    words = name.split()
    while words and words[0].lower() in _LEADING_JUNK:
        words.pop(0)
    if len(words) < 2 or words[0].lower() in _NOT_A_PLACE:  # a bare "Tribunal" names nothing
        return None
    name = " ".join(words)
    return _ALIASES.get(name, name)


def find_courts(text: str) -> list[CourtMention]:
    mentions: list[CourtMention] = []
    taken: list[tuple[int, int]] = []

    def add(name: str | None, start: int, end: int) -> None:
        if name and not any(start < e and end > s for s, e in taken):
            taken.append((start, end))
            mentions.append(CourtMention(name, start, end))

    for m in HIGH_COURT_OF.finditer(text):
        place = m.group("place")
        # "High Court of Delhi and Calcutta High Court": the part after "and" is another court.
        if " and " in place and text[m.end() :].startswith(" High Court"):
            place = place.split(" and ")[0]
        cleaned = _clean_place(place)
        add(f"High Court of {cleaned}" if cleaned else None, m.start(), m.start("place") + len(place))
    for m in PLACE_HIGH_COURT.finditer(text):
        cleaned = _clean_place(m.group("place"))
        add(f"High Court of {cleaned}" if cleaned else None, m.start(), m.end())
    for m in TRIBUNAL.finditer(text):
        add(_clean_tribunal(m.group("name")), m.start(), m.end())
    return sorted(mentions, key=lambda c: c.start)


def canonical_court(raw: str) -> str | None:
    """One name for a court as written in a sentence (used for the order under appeal)."""
    found = find_courts(raw)
    return found[0].name if found else None
