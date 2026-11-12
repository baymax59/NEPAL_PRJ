"""Find statutory provisions cited in text: "Section 438 CrPC", "Article 21", "Order VII Rule 11".

Rule-based and deliberately cautious: a section is only recorded when its Act is named right
there ("Section 302 IPC", "Section 18 of the SARFAESI Act", or a headnote such as
"Penal Code, 1860 – ss.302, 201"). A bare "s.96" or "Section 4 of the Act" is skipped: a
wrong citation in an explanation would mislead more than a missing one.

Formats were taken from the Supreme Court Reports text (see docs/steps/07-*.md), plus the FIR register
style "BNS 318(4), 316(2)" used in police records (Step 14.4).
Matching is at section level: "Section 167(2)" and "Section 167" are the same provision.
"""

import re
from dataclasses import dataclass

# Well-known Acts: every way they're written -> one short name. Other Acts keep their own name.
KNOWN_ACTS: dict[str, list[str]] = {
    "IPC": ["Indian Penal Code", "Penal Code", "I.P.C.", "IPC"],
    "CrPC": ["Code of Criminal Procedure", "Criminal Procedure Code", "Cr. P.C.", "Cr.P.C.", "Cr.PC", "CrPC"],
    "CPC": ["Code of Civil Procedure", "Civil Procedure Code", "C.P.C.", "CPC"],
    "Evidence Act": ["Indian Evidence Act", "Evidence Act"],
    "Constitution": ["Constitution of India", "Constitution"],
    "NI Act": ["Negotiable Instruments Act", "N.I. Act", "NI Act"],
    "PMLA": ["Prevention of Money Laundering Act", "PML Act", "PMLA"],
    "NDPS Act": ["Narcotic Drugs and Psychotropic Substances Act", "NDPS Act"],
    "Arbitration Act": ["Arbitration and Conciliation Act"],
    "SARFAESI Act": [
        "Securitisation and Reconstruction of Financial Assets and Enforcement of Security Interest Act",
        "SARFAESI Act",
    ],
    "DSPE Act": ["Delhi Special Police Establishment Act", "DSPE Act"],
    "SEBI Act": ["Securities and Exchange Board of India Act", "SEBI Act"],
    "PC Act": ["Prevention of Corruption Act", "PC Act"],
    "Land Acquisition Act": ["Land Acquisition Act", "L.A. Act", "LA Act"],
    # "IT Act" is left alone: it can mean the Income Tax Act or the Information Technology Act.
    # The 2023 criminal codes, likely in future police records.
    "BNS": ["Bharatiya Nyaya Sanhita", "BNS"],
    "BNSS": ["Bharatiya Nagarik Suraksha Sanhita", "BNSS"],
    "BSA": ["Bharatiya Sakshya Adhiniyam", "BSA"],
}
_ALIAS_TO_ACT = {alias: act for act, aliases in KNOWN_ACTS.items() for alias in aliases}
_KNOWN = "|".join(re.escape(a) for a in sorted(_ALIAS_TO_ACT, key=len, reverse=True))
# Any other Act: capitalised words ending in Act/Code/Sanhita/Adhiniyam ("Specific Relief Act",
# "DSPE Act"). Needs at least one word before "Act", so "the Act" / "said Act" never match.
_WORD = r"[A-Z][A-Za-z.'-]*"
_GENERIC = rf"{_WORD}(?:\s+(?:{_WORD}|of|and|for|the|to|in|on|&))*?\s+(?:Act|Code|Sanhita|Adhiniyam)\b"
_ACT = rf"(?:{_KNOWN}|{_GENERIC})(?:,?\s*\d{{4}})?"

_NUM = r"\d+[A-Z]?(?:-[A-Z])?(?:\s?\(\w{1,4}\))*"
_NUM_LIST = rf"{_NUM}(?:\s*(?:,|&|and|/)\s*{_NUM})*"

_SECTION_MARK = r"(?:Sections?|Secs?\.|ss?\.|u/s\.?)"
# "Sections 302 read with Section 34 of the IPC": the Act named at the end applies to both.
SECTION_THEN_ACT = re.compile(
    rf"\b{_SECTION_MARK}\s*(?P<nums>{_NUM_LIST})"
    rf"(?:\s*(?:read\s+with|r/w)\s+{_SECTION_MARK}\s*(?P<nums2>{_NUM_LIST}))?"
    rf"\s*(?:of\s+)?(?:the\s+)?(?P<act>{_ACT})"
)
# Headnote style: "Code of Civil Procedure, 1908 – ss.96, 105 & Or.IX, r.13 – ...", or with a
# well-known abbreviation and no year: "IPC – ss. 395, 302 and 302 r/w s.34."
# The list of references ends at the next dash or the next sentence ("s.34. Evidence Act, 1872 – s.27"
# holds two headnotes).
HEADNOTE = re.compile(
    rf"(?:(?P<act>{_KNOWN}|{_GENERIC}),\s*\d{{4}}\s*[–—-]|\b(?P<abbr>{_KNOWN})\s*[–—])"
    rf"\s*(?P<refs>(?:(?![–—]|\.\s+[A-Z]).){{1,160}})"
)
HEADNOTE_SECTIONS = re.compile(rf"\bss?\.\s?(?P<nums>{_NUM_LIST})")
# FIR register style, Act first: "BNS 318(4), 316(2)", "IPC 420/406/120B". Only for the criminal codes,
# and only 1-3 digit numbers, so the year in "IPC 1860" is never read as a section.
_CODES = "|".join(
    re.escape(alias)
    for alias in sorted((a for act in ("IPC", "CrPC", "BNS", "BNSS", "BSA") for a in KNOWN_ACTS[act]), key=len, reverse=True)
)
_SHORT_NUM = r"\d{1,3}[A-Z]?(?:\s?\(\w{1,4}\))*"
ACT_THEN_SECTIONS = re.compile(
    rf"(?<![\w.])(?P<abbr>{_CODES})\s+(?P<nums>{_SHORT_NUM}(?:\s*(?:,|&|and|/)\s*{_SHORT_NUM})*)(?!\d)"
)
ARTICLE = re.compile(rf"\bArt(?:icles?|s?\.)\s*(?P<nums>{_NUM_LIST})(?!\s+of\s+the\s+(?!Constitution)[A-Z])")
ORDER_RULE = re.compile(r"\b(?:Order|Or\.|O\.)\s*(?P<order>[IVXL]+)\s*,?\s*(?:Rule|r\.|R\.)\s*(?P<rule>\d+[A-Z]?)")


@dataclass(frozen=True)
class Provision:
    key: str  # what "the same provision" means: e.g. "crpc|section|438"
    label: str  # how it's shown: "Section 438 CrPC"
    act: str
    kind: str  # "section", "article" or "order_rule"
    number: str


_CONNECTORS = {"of", "and", "for", "the", "to", "in", "on", "&"}


def _act_name(raw: str) -> str | None:
    """Canonical Act name, or None if the text isn't a usable Act name."""
    tokens = re.sub(r",?\s*\d{4}$", "", " ".join(raw.split())).split()
    # Drop stray initials picked up in front ("J. Securities and Exchange Board of India Act").
    while tokens and re.fullmatch(r"[A-Z]\.?", tokens[0]):
        tokens.pop(0)
    if tokens and tokens[0].lower() == "the":
        tokens.pop(0)
    name = " ".join(tokens)
    if name in _ALIAS_TO_ACT:
        return _ALIAS_TO_ACT[name]
    # "B of the Act" -> "of the Act": not a named Act.
    if len(tokens) < 2 or not tokens[0][0].isupper() or tokens[-2].lower() in _CONNECTORS:
        return None
    return name


def _numbers(num_list: str) -> list[str]:
    """'302 and 34' -> ['302', '34']; '13(4)' -> ['13']; '48-A' -> ['48A']."""
    return [m.group(0).replace("-", "") for m in re.finditer(r"\d+[A-Z]?(?:-[A-Z])?", re.sub(r"\(\w+\)", "", num_list))]


def _section(act: str, number: str) -> Provision:
    if act == "Constitution":
        return _article(number)
    # "Section 302 IPC" for abbreviations, "Section 27 of the Evidence Act" for names.
    label = f"Section {number} of the {act}" if " " in act else f"Section {number} {act}"
    return Provision(f"{act.lower()}|section|{number}", label, act, "section", number)


def _article(number: str) -> Provision:
    return Provision(f"constitution|article|{number}", f"Article {number} of the Constitution", "Constitution", "article", number)


def extract_provisions(text: str) -> list[Provision]:
    """Every provision mention in `text`, in order (the same provision can appear many times)."""
    found: list[tuple[int, Provision]] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return all(end <= s or start >= e for s, e in taken)

    for match in HEADNOTE.finditer(text):
        act = _act_name(match.group("act") or match.group("abbr"))
        if act is None:
            continue
        refs_start = match.start("refs")
        for ref in HEADNOTE_SECTIONS.finditer(match.group("refs")):
            span = (refs_start + ref.start(), refs_start + ref.end())
            if free(*span):
                taken.append(span)
                found.extend((span[0], _section(act, n)) for n in _numbers(ref.group("nums")))
        for ref in ORDER_RULE.finditer(match.group("refs")):
            span = (refs_start + ref.start(), refs_start + ref.end())
            if free(*span):
                taken.append(span)
                found.append((span[0], _order_rule(ref)))

    for match in SECTION_THEN_ACT.finditer(text):
        act = _act_name(match.group("act"))
        if act is not None and free(match.start(), match.end()):
            taken.append(match.span())
            numbers = _numbers(match.group("nums")) + _numbers(match.group("nums2") or "")
            found.extend((match.start(), _section(act, n)) for n in numbers)

    for match in ACT_THEN_SECTIONS.finditer(text):
        if free(match.start(), match.end()):
            taken.append(match.span())
            act = _ALIAS_TO_ACT[match.group("abbr")]
            found.extend((match.start(), _section(act, n)) for n in _numbers(match.group("nums")))

    for match in ARTICLE.finditer(text):
        if free(match.start(), match.end()):
            taken.append(match.span())
            found.extend((match.start(), _article(n)) for n in _numbers(match.group("nums")))

    for match in ORDER_RULE.finditer(text):
        if free(match.start(), match.end()):
            taken.append(match.span())
            found.append((match.start(), _order_rule(match)))

    return [provision for _, provision in sorted(found, key=lambda item: item[0])]


def _order_rule(match: re.Match) -> Provision:
    # Orders and Rules are the structure of the Code of Civil Procedure.
    order, rule = match.group("order"), match.group("rule")
    return Provision(f"cpc|order_rule|{order}-{rule}", f"Order {order} Rule {rule} CPC", "CPC", "order_rule", f"{order}-{rule}")
