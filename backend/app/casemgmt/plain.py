"""Plain words for people: no fingerprints or codes in what screens and reports show.

Commits are identified by long codes inside the system. Some of the text the system wrote in the past (a clone's message,
a review's status note) mentions such a code. The stored text is a permanent record and is never changed; what is *shown*
passes through `plain`, which replaces a code by "an earlier update". New text is written without codes in the first place.
"""

import re

# A run of 10 or more hex digits with at least one letter (so a 10-digit phone number is not mistaken for a code).
CODE = re.compile(r"\b(?=[0-9]*[a-f])[0-9a-f]{10,64}\b")


def plain(text: str | None) -> str | None:
    return CODE.sub("an earlier update", text) if text else text
