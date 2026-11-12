"""Find calendar dates in judgment text, and the sentence each one is in.

Formats, from the Supreme Court Reports text (see docs/steps/12-*.md):
  25.12.2012 · 17-3-2018 · 18/12/2006 · 15th May 2018 · 2 May 2009 · 4th May, 1994
  April 11, 2023 · FEBRUARY 15, 2023
Every candidate must be a real calendar date ("89/7/2006" in a circular number is not).
Two-digit years ("20.05.81") are skipped: the century would be a guess.
"""

import datetime as dt
import re
from dataclasses import dataclass

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

NUMERIC = re.compile(r"(?<![\d./-])(\d{1,2})([./-])(\d{1,2})\2(\d{4})(?![\d./-]*\d)")
DAY_MONTH_YEAR = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?({_MONTH})\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
MONTH_DAY_YEAR = re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE)


@dataclass(frozen=True)
class FoundDate:
    value: dt.date
    text: str  # as written
    start: int
    end: int


def _make(year: str, month: int, day: str) -> dt.date | None:
    try:
        return dt.date(int(year), month, int(day))
    except ValueError:
        return None


def find_dates(text: str) -> list[FoundDate]:
    found: list[FoundDate] = []
    taken: list[tuple[int, int]] = []

    def add(value: dt.date | None, match: re.Match) -> None:
        if value is None or any(match.start() < e and match.end() > s for s, e in taken):
            return
        taken.append(match.span())
        found.append(FoundDate(value, match.group(0), match.start(), match.end()))

    for m in DAY_MONTH_YEAR.finditer(text):
        add(_make(m.group(3), _MONTHS[m.group(2)[:3].lower()], m.group(1)), m)
    for m in MONTH_DAY_YEAR.finditer(text):
        add(_make(m.group(3), _MONTHS[m.group(1)[:3].lower()], m.group(2)), m)
    for m in NUMERIC.finditer(text):
        add(_make(m.group(4), int(m.group(3)), m.group(1)), m)  # Indian order: day first
    return sorted(found, key=lambda d: d.start)


# Words that end with a full stop without ending the sentence ("No. 5", "Rs. 10", "M. R. Shah").
_ABBREVIATIONS = {
    "no", "nos", "rs", "mr", "mrs", "ms", "dr", "ltd", "pvt", "co", "vs", "v", "s", "ss", "sec", "art", "arts",
    "viz", "etc", "cr", "crl", "cri", "p", "pp", "para", "paras", "smt", "sh", "shri", "st", "jj", "j", "cji",
    "govt", "dept", "misc", "sl", "w.e.f", "i.e", "e.g", "u/s", "r/w", "or", "r", "inc", "hon'ble", "ors", "anr",
}
_BOUNDARY = re.compile(r"[.;?!](?=\s+[A-Z0-9(“\"'])")
MAX_SIDE_WORDS = 35


def _is_sentence_end(text: str, position: int) -> bool:
    if text[position] != ".":
        return True
    word = re.search(r"([A-Za-z.'/]+)$", text[:position])
    return not (word and (word.group(1).lower() in _ABBREVIATIONS or len(word.group(1)) == 1))


def sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing text[start:end], limited to about MAX_SIDE_WORDS words each side."""
    begin = 0
    for m in _BOUNDARY.finditer(text, 0, start):
        if _is_sentence_end(text, m.start()):
            begin = m.end()
    finish = len(text)
    for m in _BOUNDARY.finditer(text, end):
        if _is_sentence_end(text, m.start()):
            finish = m.start() + 1
            break
    # Cut the original text at word boundaries (rather than re-joining words), so punctuation
    # stays exactly as written: "05.03.2018." not "05.03.2018 .".
    words_before = list(re.finditer(r"\S+", text[begin:start]))
    words_after = list(re.finditer(r"\S+", text[end:finish]))
    clipped_before = len(words_before) > MAX_SIDE_WORDS
    clipped_after = len(words_after) > MAX_SIDE_WORDS
    cut_start = begin + words_before[-MAX_SIDE_WORDS].start() if clipped_before else begin
    cut_end = end + words_after[MAX_SIDE_WORDS - 1].end() if clipped_after else finish
    sentence = " ".join(text[cut_start:cut_end].split())
    return ("… " if clipped_before else "") + sentence + (" …" if clipped_after else "")
