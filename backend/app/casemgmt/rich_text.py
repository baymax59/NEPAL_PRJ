"""The styled copy of a case's description (bold, colours, lists...), made safe before it is stored.

The plain description (`description`) stays the text that reports, searches, the assistant and the history read. The styled copy
(`description_html`) is only for showing the description on the case page the way its writer formatted it. It is cleaned here, once,
whoever sends it: only the formatting the editor offers survives; scripts, links, images, event handlers and every other style are dropped.
"""
import re

import nh3

TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "span"}
ATTRIBUTES = {"p": {"style"}, "span": {"style"}, "li": {"style"}}

# The only styles the editor makes, and the only values accepted for each.
_STYLES = {
    "color": re.compile(r"#[0-9a-fA-F]{3,8}|rgba?\(\s*\d{1,3}\s*(,\s*\d{1,3}\s*){2}(,\s*(0|1|0?\.\d{1,3})\s*)?\)|[a-zA-Z]{3,20}"),
    "font-family": re.compile(r"[A-Za-z0-9 ,'\"-]{1,120}"),
    "font-size": re.compile(r"\d{1,3}(\.\d{1,2})?(px|pt|em|rem|%)"),
    "text-align": re.compile(r"left|right|center|justify"),
}
MAX_LENGTH = 100_000


def _safe_style(value: str) -> str | None:
    kept = []
    for declaration in value.split(";"):
        name, _, setting = declaration.partition(":")
        name, setting = name.strip().lower(), setting.strip()
        rule = _STYLES.get(name)
        if rule is not None and rule.fullmatch(setting):
            kept.append(f"{name}: {setting}")
    return "; ".join(kept) or None


def _attribute(tag: str, name: str, value: str) -> str | None:
    return _safe_style(value) if name == "style" else None


def clean(html: str | None) -> str | None:
    """The html with only the allowed formatting left; None when nothing is left to show."""
    if not html or not html.strip():
        return None
    cleaned = nh3.clean(html[:MAX_LENGTH * 2], tags=TAGS, attributes=ATTRIBUTES, attribute_filter=_attribute, strip_comments=True)
    return cleaned[:MAX_LENGTH] if cleaned.strip() and re.sub(r"<[^>]*>", "", cleaned).strip() else None
