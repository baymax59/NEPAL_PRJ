"""Case Management CM-2: a file's type comes from its bytes, and must agree with its name."""

import pytest

from app.casemgmt.errors import Unsupported
from app.casemgmt.filetypes import check

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

ACCEPTED = [
    (b"%PDF-1.7\n", "statement.pdf", "application/pdf", "document", False),
    (b"\x89PNG\r\n\x1a\n....", "screenshot.png", "image/png", "image", False),
    (b"\xff\xd8\xff\xe0..JFIF", "photo.JPG", "image/jpeg", "image", False),
    (b"\x00\x00\x00\x18ftypheic....", "IMG_0001.HEIC", "image/heic", "image", False),
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", "call.wav", "audio/wav", "audio", False),
    (b"#!AMR\n....", "call-recording.amr", "audio/amr", "audio", False),
    (b"\x00\x00\x00\x18ftypisom....", "cctv.mp4", "video/mp4", "video", False),
    (b"PK\x03\x04....", "report.docx", DOCX, "document", False),
    (b"PK\x03\x04....", "chats.zip", "application/zip", "archive", False),
    (b"PK\x03\x04....", "suspect-app.apk", "application/vnd.android.package-archive", "executable", True),
    (b"SQLite format 3\x00....", "msgstore.db", "application/vnd.sqlite3", "data", False),
    (b"\xd4\xc3\xb2\xa1....", "capture.pcap", "application/vnd.tcpdump.pcap", "data", False),
    (b"EVF\x09\x0d\x0a\xff\x00....", "phone.E01", "application/x-ewf", "data", False),
    (b"\x00\x13\x37\xfe\xff\x00", "disk.dd", "application/octet-stream", "data", False),  # raw images have no signature
    (b"caller,callee\nA,B\n", "cdr.csv", "text/csv", "text", False),
    (b"Caf\xe9 owner's statement\r\n", "statement.txt", "text/plain", "text", False),  # an older Windows encoding
    (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "logo.svg", "image/svg+xml", "image", True),
    (b"#!/bin/sh\necho hi\n", "dropper.sh", "text/x-script", "text", True),
    (b"MZ\x90\x00....", "sample.exe", "application/vnd.microsoft.portable-executable", "executable", True),
    (b"\x00\x01\x02 unknown", "blob", "application/octet-stream", "binary", False),  # no name, no known type
]


@pytest.mark.parametrize(("head", "name", "mime", "category", "active"), ACCEPTED)
def test_types_are_recognised_from_their_bytes(head, name, mime, category, active):
    found = check(head, name)
    assert (found.mime, found.category, found.active) == (mime, category, active)


REFUSED = [
    (b"MZ\x90\x00....", "invoice.pdf"),  # a Windows program dressed as a document
    (b"\x7fELF....", "holiday.jpg"),
    (b"\x7fELF....", "payload"),  # programs need their real extension
    (b"just some words", "photo.png"),
    (b"%PDF-1.4", "notes.txt"),
    (b"\x00\x01\x02 binary", "notes.txt"),
    (b"\x89PNG\r\n\x1a\n", "song.mp3"),
]


@pytest.mark.parametrize(("head", "name"), REFUSED)
def test_content_that_contradicts_the_name_is_refused(head, name):
    with pytest.raises(Unsupported):
        check(head, name)


def test_programs_can_be_refused_altogether():
    with pytest.raises(Unsupported, match="doesn't accept programs"):
        check(b"MZ\x90\x00", "sample.exe", accept_programs=False)
