"""Text extraction from PDF, Word and plain-text files."""

import docx
import pytest

from app.documents.extract import ExtractionError, extract


def test_pdf_text_is_extracted_page_by_page(make_pdf):
    path = make_pdf("judgment.pdf", [["The appellant filed a suit.", "It was decreed."], ["The appeal is allowed."]])

    result = extract(path)

    assert [p.number for p in result.pages] == [1, 2]
    assert "The appellant filed a suit." in result.pages[0].text
    assert "The appeal is allowed." in result.pages[1].text
    assert result.has_page_numbers
    assert result.extractor.startswith("pypdfium2 ")
    assert result.mime_type == "application/pdf"


def test_image_only_pages_are_detected(make_pdf):
    result = extract(make_pdf("scan.pdf", [None, ["Some text"]]))

    assert result.pages[0].has_images
    assert result.pages[0].text.strip() == ""


def test_word_paragraphs_and_tables_are_extracted(tmp_path):
    document = docx.Document()
    document.add_paragraph("Statement of facts.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Date"
    table.rows[0].cells[1].text = "12-03-2021"
    document.save(tmp_path / "facts.docx")

    result = extract(tmp_path / "facts.docx")

    assert len(result.pages) == 1
    assert result.pages[0].number is None
    assert not result.has_page_numbers
    assert "Statement of facts." in result.pages[0].text
    assert "Date | 12-03-2021" in result.pages[0].text


def test_plain_text_is_read_as_utf8(tmp_path):
    (tmp_path / "note.txt").write_text("Costs of ₹2,00,000 imposed.", encoding="utf-8")

    result = extract(tmp_path / "note.txt")

    assert result.pages[0].text == "Costs of ₹2,00,000 imposed."


def test_damaged_pdf_gives_a_clear_error(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4\nthis is not really a pdf")

    with pytest.raises(ExtractionError, match="could not be opened"):
        extract(tmp_path / "broken.pdf")


def test_file_type_is_decided_by_content_not_name(tmp_path):
    (tmp_path / "fake.pdf").write_bytes(b"<html>not a pdf</html>")

    with pytest.raises(ExtractionError, match="Unsupported file type"):
        extract(tmp_path / "fake.pdf")
