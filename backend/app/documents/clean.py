"""Clean extracted page text: remove page furniture, keep the content.

Rules come from inspecting the real Supreme Court Reports PDFs (see docs/steps/04-*.md),
but are written generically so they also suit other sources:
- Lines that are a single capital letter (SCR margin markers A-H) or only a number
  (page numbers, footnote markers) are removed.
- Running headers/footers are found by repetition: a line near the top or bottom of a page
  that recurs on many pages of the same document (ignoring digits) is removed there.
- Lines are joined into running text; numbered paragraphs ("12. ...") start a new line.
Nothing is reworded. Cleaning only removes layout noise and joins broken lines.
"""

import re
from collections import Counter

# Characters pdfium emits that aren't meant literally.
CHARACTER_FIXES = str.maketrans(
    {
        "￾": "-",  # pdfium's marker for a hyphen in compound words ("tax-payer")
        "­": "",  # soft hyphen
        "": "•",  # bullet from the Symbol font (private-use code point)
        "": " ",  # space from the Symbol font
    }
)

SINGLE_LETTER = re.compile(r"^[A-Z]$")
NUMBER_ONLY = re.compile(r"^\d{1,4}$")
NUMBERED_PARAGRAPH = re.compile(r"^\d{1,3}\.\s+\S")

EDGE_LINES = 3  # how many lines at the top and bottom of a page can be headers/footers
MIN_PAGES_FOR_REPETITION = 4  # too few pages to tell a header from content
MIN_SHARE_OF_PAGES = 0.3  # headers that alternate on odd/even pages appear on ~50%
# A line that *starts with* a repeated header also counts as that header. pdfium sometimes
# merges a header with another line on the first page, e.g.
# "362 SUPREME COURT REPORTS [2022] 3 S.C.R. [2022] 3 S.C.R. 362". Only long headers are
# matched this way, so short repeated fragments ("v.") never remove real sentences.
MIN_PREFIX_CHARS = 20


def _signature(line: str) -> str:
    """Compare lines ignoring digits and case, so "204 SUPREME COURT REPORTS" matches "206 ..."."""
    return re.sub(r"\d+", "#", line.lower())


def _matches(signature: str, header: str) -> bool:
    return signature == header or (len(header) >= MIN_PREFIX_CHARS and signature.startswith(header + " "))


def _content_lines(raw: str) -> list[str]:
    lines = (line.strip() for line in raw.translate(CHARACTER_FIXES).splitlines())
    return [line for line in lines if line and not SINGLE_LETTER.match(line) and not NUMBER_ONLY.match(line)]


def _repeated(edges: list[list[str]]) -> set[str]:
    """Signatures recurring in the same position (top or bottom) on enough pages.

    Top and bottom are checked separately: a document's first line (e.g. a party name) can be
    the start of a running title printed at the *bottom* of later pages, and must be kept.
    """
    signatures = [{_signature(line) for line in edge} for edge in edges]
    candidates = set().union(*signatures)
    counts = Counter(
        candidate for candidate in candidates for page in signatures if any(_matches(s, candidate) for s in page)
    )
    threshold = max(2, MIN_SHARE_OF_PAGES * len(edges))
    return {signature for signature, n in counts.items() if n >= threshold}


def _is_header(line: str, repeated: set[str]) -> bool:
    signature = _signature(line)
    return any(_matches(signature, header) for header in repeated)


def _strip_edges(lines: list[str], top: set[str], bottom: set[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < min(EDGE_LINES, end) and _is_header(lines[start], top):
        start += 1
    while end > max(start, len(lines) - EDGE_LINES) and _is_header(lines[end - 1], bottom):
        end -= 1
    return lines[start:end]


def _join(lines: list[str]) -> str:
    text = ""
    for line in lines:
        if not text:
            text = line
        elif NUMBERED_PARAGRAPH.match(line):
            text += "\n" + line
        elif text.endswith("-"):
            text += line  # word broken across lines: keep the hyphen, drop the gap
        else:
            text += " " + line
    return re.sub(r"[ \t]+", " ", text)


# Words broken after a typographic ligature (fi, fl, ff), with a real space in the PDF:
# "off ence", "fi led", "Offi cer". About 2,500 cases in the first 100 judgments.
LIGATURE_SPLIT = re.compile(r"\b([A-Za-z]*(?:fi|fl|ff)) ([a-z]+)\b")
WORD = re.compile(r"[A-Za-z]+")


def _rejoin_ligature_splits(pages: list[str]) -> list[str]:
    """Join ligature-split words, deciding per document so real word pairs stay apart.

    A piece is a "fragment" if it never appears on its own anywhere else in the document
    ("fi", "offi", "ence" don't; "plaintiff", "has", "date" do).
    - Left piece ends in fi/fl: English words almost never do, so join if it's a fragment.
    - Left piece ends in ff: many real words do ("off", "staff", "plaintiff"), so join only
      if the right piece is a fragment starting with a vowel ("ence", "ect", "erent").
    """
    text = "\n".join(pages)
    splits = list(LIGATURE_SPLIT.finditer(text))
    if not splits:
        return pages
    word_counts = Counter(w.lower() for w in WORD.findall(text))
    as_left = Counter(m.group(1).lower() for m in splits)
    as_right = Counter(m.group(2) for m in splits)

    def join(match: re.Match) -> str:
        left, right = match.group(1), match.group(2)
        if left.lower().endswith("ff"):
            right_is_fragment = word_counts[right] == as_right[right]
            should_join = right_is_fragment and right[0] in "aeiouy"
        else:
            should_join = word_counts[left.lower()] == as_left[left.lower()]
        return left + right if should_join else match.group(0)

    return [LIGATURE_SPLIT.sub(join, page) for page in pages]


def clean_pages(raw_pages: list[str]) -> list[str]:
    """Clean every page of one document. Returns one string per page, in the same order."""
    pages = [_content_lines(raw) for raw in raw_pages]
    if len(pages) >= MIN_PAGES_FOR_REPETITION:
        top = _repeated([lines[:EDGE_LINES] for lines in pages])
        bottom = _repeated([lines[-EDGE_LINES:] for lines in pages])
    else:
        top = bottom = set()
    return _rejoin_ligature_splits([_join(_strip_edges(lines, top, bottom)) for lines in pages])
