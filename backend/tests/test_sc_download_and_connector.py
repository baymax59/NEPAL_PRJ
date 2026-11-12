"""Downloading the subset and reading it back, against a fake in-memory bucket (no internet)."""

import io

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.connectors.sc_judgments.connector import SupremeCourtConnector
from app.connectors.sc_judgments.download import DownloadError, choose_sample, download_file, download_subset
from app.connectors.sc_judgments.source import RAW_DIR, metadata_key, pdf_key
from app.schemas.case_record import CaseRecord

FAKE_PDF = b"%PDF-1.7\n fake judgment \n%%EOF"


def metadata_row(path: str, cnr: str, languages: str = "ENG,HIN") -> dict:
    return {
        "title": f"PETITIONER {cnr} versus RESPONDENT",
        "petitioner": f"PETITIONER {cnr}",
        "respondent": "RESPONDENT",
        "description": "",
        "judge": "TEST JUDGE",
        "author_judge": None,
        "citation": "[2023] 1 S.C.R. 1",
        "case_id": "2023 INSC 1",
        "cnr": cnr,
        "decision_date": "01-02-2023",
        "disposal_nature": "Dismissed",
        "court": "Supreme Court of India",
        "available_languages": languages,
        "raw_html": "<select></select>",
        "path": path,
        "nc_display": "2023INSC1",
        "scraped_at": "2025-06-12T21:53:00",
        "year": "2023",
    }


def parquet_bytes(rows: list[dict]) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buffer)
    return buffer.getvalue()


class FakeBucket:
    """Answers like the S3 bucket for the files it holds, 404 for anything else."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.requested: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        key = request.url.path.lstrip("/")
        self.requested.append(key)
        if key in self.files:
            return httpx.Response(200, content=self.files[key])
        return httpx.Response(404, content=b"<Error><Code>NoSuchKey</Code></Error>")

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))


@pytest.fixture
def bucket():
    rows = [
        metadata_row("2023_1_1_10", "CNR0000000001"),
        metadata_row("2023_1_11_20", "CNR0000000002"),  # its PDF is missing from the bucket
        metadata_row("2023_1_21_30", "CNR0000000003", languages="HIN"),  # no English version
    ]
    return FakeBucket(
        {
            metadata_key(2023): parquet_bytes(rows),
            pdf_key(2023, "2023_1_1_10"): FAKE_PDF,
        }
    )


def quiet(_message: str) -> None:
    pass


def test_download_file_saves_content_and_checksum(tmp_path, bucket):
    key = pdf_key(2023, "2023_1_1_10")
    entry = download_file(bucket.client(), key, tmp_path, max_bytes=1_000_000, expect_pdf=True)

    assert (tmp_path / key).read_bytes() == FAKE_PDF
    assert entry.size_bytes == len(FAKE_PDF)
    assert len(entry.sha256) == 64


def test_download_rejects_a_page_that_is_not_a_pdf(tmp_path):
    html = FakeBucket({pdf_key(2023, "x"): b"<html>Access denied</html>"})

    with pytest.raises(DownloadError, match="not a PDF"):
        download_file(html.client(), pdf_key(2023, "x"), tmp_path, max_bytes=1_000_000, expect_pdf=True)
    assert not list(tmp_path.rglob("*.pdf*"))  # nothing half-written left behind


def test_download_rejects_oversized_files(tmp_path):
    big = FakeBucket({pdf_key(2023, "x"): b"%PDF-" + b"0" * 2000})

    with pytest.raises(DownloadError, match="larger than"):
        download_file(big.client(), pdf_key(2023, "x"), tmp_path, max_bytes=1000, expect_pdf=True)


def test_unsafe_file_keys_from_the_source_are_refused():
    with pytest.raises(ValueError, match="Unsafe"):
        pdf_key(2023, "../../etc/passwd")


def test_sample_is_reproducible_and_a_bigger_sample_contains_the_smaller():
    paths = [f"p{i}" for i in range(100)]

    assert choose_sample(paths, 10, seed=42, year=2023) == choose_sample(paths, 10, seed=42, year=2023)
    assert set(choose_sample(paths, 10, 42, 2023)) <= set(choose_sample(paths, 20, 42, 2023))
    assert choose_sample(paths, 10, 42, 2023) != choose_sample(paths, 10, 7, 2023)


def test_download_subset_records_successes_and_failures(tmp_path, bucket):
    manifest = download_subset(bucket.client(), tmp_path, [2023], per_year=5, progress=quiet)

    assert manifest.selected[2023] == ["2023_1_11_20", "2023_1_1_10"]  # Hindi-only row not eligible
    assert list(manifest.pdfs) == ["2023_1_1_10"]
    assert manifest.failed == {"2023_1_11_20": "HTTP 404"}
    assert (tmp_path / RAW_DIR / "manifest.json").exists()


def test_rerunning_download_skips_files_already_present(tmp_path, bucket):
    download_subset(bucket.client(), tmp_path, [2023], per_year=5, progress=quiet)
    bucket.requested.clear()

    download_subset(bucket.client(), tmp_path, [2023], per_year=5, progress=quiet)

    # Only the previously failed PDF is tried again.
    assert bucket.requested == [pdf_key(2023, "2023_1_11_20")]


def test_connector_yields_only_selected_rows_with_honest_warnings(tmp_path, bucket):
    download_subset(bucket.client(), tmp_path, [2023], per_year=5, progress=quiet)

    records = list(SupremeCourtConnector(tmp_path).iter_records())

    assert all(isinstance(r, CaseRecord) for r in records)
    by_cnr = {r.source_record_id: r for r in records}
    assert set(by_cnr) == {"CNR0000000001", "CNR0000000002"}
    assert len(by_cnr["CNR0000000001"].documents) == 1
    assert by_cnr["CNR0000000002"].documents == []
    assert by_cnr["CNR0000000002"].warnings == ["Judgment PDF not available (HTTP 404)"]


def test_connector_notices_a_downloaded_pdf_that_was_deleted(tmp_path, bucket):
    download_subset(bucket.client(), tmp_path, [2023], per_year=5, progress=quiet)
    (tmp_path / RAW_DIR / pdf_key(2023, "2023_1_1_10")).unlink()

    records = {r.source_record_id: r for r in SupremeCourtConnector(tmp_path).iter_records()}

    assert records["CNR0000000001"].documents == []
    assert "missing from the data folder" in records["CNR0000000001"].warnings[0]


def test_connector_explains_what_to_do_when_nothing_was_downloaded(tmp_path):
    with pytest.raises(FileNotFoundError, match="sc_download"):
        SupremeCourtConnector(tmp_path)
