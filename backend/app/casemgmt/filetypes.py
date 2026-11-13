"""What an evidence file really is, decided from its first bytes (docs/case-management/07 §7).

The name a file arrives with is only a claim. A file whose content contradicts its name (a program called
"statement.pdf", a text file called "photo.jpg") is refused: renaming files to slip them past checks is
exactly what this guards against. Files with an honest name are accepted whatever they are, because almost
anything can be evidence; programs, scripts, HTML and SVG are marked as active content, and the application
never runs, previews or renders them (downloads are always sent as plain data, as an attachment).
"""

import codecs
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.casemgmt.enums import FileCategory as C
from app.casemgmt.errors import Unsupported

HEAD_BYTES = 8192  # how much of the start of a file the checks look at


@dataclass(frozen=True)
class FileType:
    mime: str
    category: C
    label: str
    active: bool = False  # could run, or render as a page, if opened: never previewed or opened inline


def _t(mime: str, category: C, label: str, active: bool = False) -> FileType:
    return FileType(mime, category, label, active)


PDF = _t("application/pdf", C.DOCUMENT, "PDF document")
GIF = _t("image/gif", C.IMAGE, "GIF image")
TIFF = _t("image/tiff", C.IMAGE, "TIFF image")
MP3 = _t("audio/mpeg", C.AUDIO, "MP3 audio")
PCAP = _t("application/vnd.tcpdump.pcap", C.DATA, "network packet capture")
MACHO = _t("application/x-mach-binary", C.EXECUTABLE, "macOS program", True)
BINARY = _t("application/octet-stream", C.BINARY, "unrecognised binary data")
RAW_DATA = _t("application/octet-stream", C.DATA, "raw data or disk image")

# (offset, signature, type). Checked in order; the first match wins.
SIGNATURES: list[tuple[int, bytes, FileType]] = [
    (0, b"%PDF-", PDF),
    (0, b"\x89PNG\r\n\x1a\n", _t("image/png", C.IMAGE, "PNG image")),
    (0, b"\xff\xd8\xff", _t("image/jpeg", C.IMAGE, "JPEG image")),
    (0, b"GIF87a", GIF),
    (0, b"GIF89a", GIF),
    (0, b"II*\x00", TIFF),
    (0, b"MM\x00*", TIFF),
    (0, b"\x1a\x45\xdf\xa3", _t("video/x-matroska", C.VIDEO, "Matroska / WebM video")),
    (0, b"ID3", MP3),
    (0, b"OggS", _t("audio/ogg", C.AUDIO, "Ogg audio")),
    (0, b"fLaC", _t("audio/flac", C.AUDIO, "FLAC audio")),
    (0, b"#!AMR", _t("audio/amr", C.AUDIO, "AMR audio (phone recording)")),
    (0, b"7z\xbc\xaf\x27\x1c", _t("application/x-7z-compressed", C.ARCHIVE, "7-Zip archive")),
    (0, b"Rar!\x1a\x07", _t("application/vnd.rar", C.ARCHIVE, "RAR archive")),
    (0, b"\x1f\x8b", _t("application/gzip", C.ARCHIVE, "gzip archive")),
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", _t("application/x-ole-storage", C.DOCUMENT, "Office 97-2003 or Outlook file")),
    (0, b"\xd4\xc3\xb2\xa1", PCAP),
    (0, b"\xa1\xb2\xc3\xd4", PCAP),
    (0, b"\x4d\x3c\xb2\xa1", PCAP),
    (0, b"\xa1\xb2\x3c\x4d", PCAP),
    (0, b"\x0a\x0d\x0d\x0a", _t("application/x-pcapng", C.DATA, "network packet capture (pcapng)")),
    (0, b"EVF\x09\x0d\x0a\xff\x00", _t("application/x-ewf", C.DATA, "EnCase forensic image (E01)")),
    (0, b"SQLite format 3\x00", _t("application/vnd.sqlite3", C.DATA, "SQLite database")),
    (0, b"MZ", _t("application/vnd.microsoft.portable-executable", C.EXECUTABLE, "Windows program", True)),
    (0, b"\x7fELF", _t("application/x-elf", C.EXECUTABLE, "Linux program", True)),
    (0, b"\xcf\xfa\xed\xfe", MACHO),
    (0, b"\xce\xfa\xed\xfe", MACHO),
    (0, b"dex\n", _t("application/vnd.android.dex", C.EXECUTABLE, "Android program code", True)),
]

# Zip-based formats: told apart by their name (their content is a zip archive either way).
ZIP_FORMATS = {
    "docx": _t("application/vnd.openxmlformats-officedocument.wordprocessingml.document", C.DOCUMENT, "Word document"),
    "xlsx": _t("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", C.DOCUMENT, "Excel spreadsheet"),
    "pptx": _t("application/vnd.openxmlformats-officedocument.presentationml.presentation", C.DOCUMENT, "PowerPoint file"),
    "odt": _t("application/vnd.oasis.opendocument.text", C.DOCUMENT, "OpenDocument text"),
    "ods": _t("application/vnd.oasis.opendocument.spreadsheet", C.DOCUMENT, "OpenDocument spreadsheet"),
    "apk": _t("application/vnd.android.package-archive", C.EXECUTABLE, "Android app", True),
    "jar": _t("application/java-archive", C.EXECUTABLE, "Java program", True),
}
ZIP = _t("application/zip", C.ARCHIVE, "zip archive")
SCRIPT_SUFFIXES = {"js", "vbs", "ps1", "bat", "cmd", "sh", "py"}
TEXT_BY_SUFFIX = {
    "csv": _t("text/csv", C.TEXT, "CSV table"),
    "json": _t("application/json", C.TEXT, "JSON data"),
    "eml": _t("message/rfc822", C.TEXT, "e-mail message"),
    "md": _t("text/markdown", C.TEXT, "Markdown text"),
}

# What a name promises. A name not listed here promises nothing, and the content decides.
EXPECTED: dict[str, C] = {
    **dict.fromkeys(["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "rtf", "msg"], C.DOCUMENT),
    **dict.fromkeys(["jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "heic", "heif", "svg"], C.IMAGE),
    **dict.fromkeys(["mp3", "wav", "m4a", "ogg", "oga", "opus", "amr", "flac", "aac"], C.AUDIO),
    **dict.fromkeys(["mp4", "m4v", "mov", "avi", "mkv", "webm", "3gp"], C.VIDEO),
    **dict.fromkeys(["zip", "7z", "rar", "gz", "tgz"], C.ARCHIVE),
    **dict.fromkeys(["txt", "csv", "json", "log", "xml", "eml", "md", "html", "htm", *SCRIPT_SUFFIXES], C.TEXT),
    **dict.fromkeys(["pcap", "pcapng", "e01", "db", "sqlite", "sqlite3", "dd", "raw", "img", "iso", "mem"], C.DATA),
    **dict.fromkeys(["exe", "dll", "elf", "so", "apk", "jar", "dex"], C.EXECUTABLE),
}


def suffix(filename: str) -> str:
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower().lstrip(".")


def _riff_or_ftyp(head: bytes) -> FileType | None:
    if head[:4] == b"RIFF":
        return {b"WAVE": _t("audio/wav", C.AUDIO, "WAV audio"), b"AVI ": _t("video/x-msvideo", C.VIDEO, "AVI video"),
                b"WEBP": _t("image/webp", C.IMAGE, "WebP image")}.get(head[8:12])
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
            return _t("image/heic", C.IMAGE, "HEIC image (phone photo)")
        if brand == b"qt  ":
            return _t("video/quicktime", C.VIDEO, "QuickTime video")
        if brand.startswith(b"3g"):
            return _t("video/3gpp", C.VIDEO, "3GP video (phone)")
        if brand in (b"M4A ", b"M4B "):
            return _t("audio/mp4", C.AUDIO, "M4A audio")
        return _t("video/mp4", C.VIDEO, "MP4 video")
    return None


def _looks_like_text(head: bytes) -> bool:
    """No NUL bytes and valid UTF-8, or (for older Windows exports) almost only printable bytes."""
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return True
    if b"\x00" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)  # a cut-off last character is fine
        return True
    except UnicodeDecodeError:
        printable = sum(1 for b in head if b >= 0x20 or b in b"\t\n\r\f")
        return printable >= 0.95 * len(head)


def _text_type(head: bytes, ext: str) -> FileType:
    start = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if start.startswith((b"<!doctype html", b"<html")) or b"<script" in start[:2048]:
        return _t("text/html", C.TEXT, "HTML page", True)
    if start.startswith(b"<") and b"<svg" in start[:2048]:
        return _t("image/svg+xml", C.IMAGE, "SVG drawing (can contain scripts)", True)
    if start.startswith(b"<?xml"):
        return _t("application/xml", C.TEXT, "XML data")
    if start.startswith(b"{\\rtf"):
        return _t("application/rtf", C.DOCUMENT, "RTF document")
    if start.startswith(b"#!") or ext in SCRIPT_SUFFIXES:
        return _t("text/x-script", C.TEXT, "script", True)
    return TEXT_BY_SUFFIX.get(ext, _t("text/plain", C.TEXT, "plain text"))


def sniff(head: bytes, filename: str = "") -> FileType:
    """The file's type from its first bytes (and, only to tell zip-based formats apart, its name)."""
    ext = suffix(filename)
    for offset, signature, found in SIGNATURES:
        if head[offset:offset + len(signature)] == signature:
            return found
    if found := _riff_or_ftyp(head):
        return found
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return ZIP_FORMATS.get(ext, ZIP)
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0:  # an MP3 / AAC frame without a tag
        return MP3
    if head[:2] == b"BM" and ext in ("bmp", "dib"):  # too short a signature to trust on its own
        return _t("image/bmp", C.IMAGE, "BMP image")
    if _looks_like_text(head):
        return _text_type(head, ext)
    return BINARY


def check(head: bytes, filename: str, *, accept_programs: bool = True) -> FileType:
    """The file's type, if its content agrees with its name; otherwise Unsupported (415)."""
    ext = suffix(filename)
    found = sniff(head, filename)
    expected = EXPECTED.get(ext)
    shown = f".{ext}" if ext else "a name without an extension"
    if found.category == C.EXECUTABLE and expected != C.EXECUTABLE:
        raise Unsupported(f"This file is a {found.label} but is named with {shown}. Disguised files are refused; "
                          "if it is evidence, upload it under a name with its real extension.")
    if found.category == C.EXECUTABLE and not accept_programs:
        raise Unsupported(f"This file is a {found.label}. This installation doesn't accept programs as evidence.")
    if expected is None or found.category == expected:
        return found
    if expected == C.DATA and found.category == C.BINARY:  # disk and memory images have no signature
        return RAW_DATA
    raise Unsupported(f"The file's content ({found.label}) doesn't match its name ({shown}). "
                      "Check that it is the right file; renamed files are refused.")
