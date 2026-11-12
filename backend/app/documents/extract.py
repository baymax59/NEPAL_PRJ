"""Get raw text out of PDF, Word and plain-text files, page by page where pages exist.

PDFs use pypdfium2 (BSD-3/Apache-2.0, built on Chrome's PDF engine). PyMuPDF was not used
because it is AGPL-licensed. Extraction is kept in this one module so the library can be
swapped without touching anything else.

The file type is decided from the file's content, not just its name.
"""

import importlib.metadata
import zipfile
from dataclasses import dataclass
from pathlib import Path

import docx
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"  # .docx files are zip archives

# Limits for files from users: a tiny .docx can unpack to gigabytes ("zip bomb"), and a huge
# PDF would tie up the server.
MAX_DOCX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 1000


class ExtractionError(Exception):
    """The file could not be read. The message is safe to show to users."""


@dataclass
class ExtractedPage:
    number: int | None  # 1-based; None for formats without fixed pages
    text: str
    has_images: bool = False


@dataclass
class ExtractedDocument:
    pages: list[ExtractedPage]
    extractor: str  # library name and version, kept for provenance
    has_page_numbers: bool
    mime_type: str


def _version(package: str) -> str:
    return f"{package} {importlib.metadata.version(package)}"


def extract(path: Path) -> ExtractedDocument:
    with path.open("rb") as f:
        head = f.read(8)

    if head.startswith(PDF_MAGIC):
        return _extract_pdf(path)
    if head.startswith(ZIP_MAGIC) and path.suffix.lower() == ".docx":
        return _extract_docx(path)
    if path.suffix.lower() == ".txt":
        return _extract_txt(path)
    raise ExtractionError("Unsupported file type: only PDF, Word (.docx) and plain text (.txt) are supported")


def _extract_pdf(path: Path) -> ExtractedDocument:
    try:
        pdf = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        reason = "password-protected" if "password" in str(exc).lower() else "damaged or not a valid PDF"
        raise ExtractionError(f"PDF could not be opened ({reason})") from exc

    try:
        if len(pdf) > MAX_PDF_PAGES:
            raise ExtractionError(f"PDF has {len(pdf)} pages; the limit is {MAX_PDF_PAGES}")
        pages = []
        for index in range(len(pdf)):
            page = pdf[index]
            text = page.get_textpage().get_text_range()
            has_images = any(True for _ in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]))
            pages.append(ExtractedPage(number=index + 1, text=text, has_images=has_images))
    finally:
        pdf.close()

    return ExtractedDocument(
        pages=pages, extractor=_version("pypdfium2"), has_page_numbers=True, mime_type="application/pdf"
    )


def _extract_docx(path: Path) -> ExtractedDocument:
    try:
        with zipfile.ZipFile(path) as archive:
            unpacked = sum(entry.file_size for entry in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise ExtractionError("Word document could not be opened (damaged or not a .docx file)") from exc
    if unpacked > MAX_DOCX_UNPACKED_BYTES:
        raise ExtractionError("Word document is too large once unpacked")

    try:
        document = docx.Document(str(path))
    except Exception as exc:  # python-docx raises several unrelated types for bad files
        raise ExtractionError("Word document could not be opened (damaged or not a .docx file)") from exc

    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return ExtractedDocument(
        pages=[ExtractedPage(number=None, text="\n".join(parts))],
        extractor=_version("python-docx"),
        has_page_numbers=False,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _extract_txt(path: Path) -> ExtractedDocument:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExtractionError("Text file is not valid UTF-8") from exc
    return ExtractedDocument(
        pages=[ExtractedPage(number=None, text=text)],
        extractor="plain-text",
        has_page_numbers=False,
        mime_type="text/plain",
    )
