"""Download a small, reproducible subset of the Supreme Court dataset.

For each year: fetch the metadata Parquet file, pick a seeded random sample of judgments,
and fetch their English PDFs. Already-downloaded files are skipped, so the command can be
re-run safely (e.g. after a network error) and a larger --per-year adds to the existing subset.
"""

import datetime as dt
import hashlib
import logging
import random
from collections.abc import Callable
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from app.connectors.sc_judgments.manifest import FileEntry, Manifest
from app.connectors.sc_judgments.source import (
    MANIFEST_NAME,
    RAW_DIR,
    SAFE_PATH_KEY,
    metadata_key,
    pdf_key,
    url_for,
)

logger = logging.getLogger(__name__)

MAX_METADATA_BYTES = 50 * 1024 * 1024
MAX_PDF_BYTES = 50 * 1024 * 1024


class DownloadError(Exception):
    pass


def download_file(client: httpx.Client, key: str, raw_dir: Path, *, max_bytes: int, expect_pdf: bool) -> FileEntry:
    """Stream one file to raw_dir/key, checking size and type. Returns its manifest entry."""
    url = url_for(key)
    dest = raw_dir / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise DownloadError(f"HTTP {response.status_code}")
            with tmp.open("wb") as out:
                for chunk in response.iter_bytes():
                    if size == 0 and expect_pdf and not chunk.startswith(b"%PDF-"):
                        raise DownloadError("Response is not a PDF")
                    size += len(chunk)
                    if size > max_bytes:
                        raise DownloadError(f"File larger than {max_bytes // (1024 * 1024)} MB")
                    digest.update(chunk)
                    out.write(chunk)
        if size == 0:
            raise DownloadError("Empty response")
        tmp.replace(dest)
    except httpx.HTTPError as exc:
        raise DownloadError(f"Network error: {type(exc).__name__}") from exc
    finally:
        tmp.unlink(missing_ok=True)

    return FileEntry(
        key=key,
        source_uri=url,
        sha256=digest.hexdigest(),
        size_bytes=size,
        retrieved_at=dt.datetime.now(dt.UTC),
    )


def eligible_paths(parquet_file: Path) -> list[str]:
    """`path` values of rows that have an English judgment and a safe file key, sorted."""
    table = pq.read_table(parquet_file, columns=["path", "available_languages"])
    paths = {
        row["path"]
        for row in table.to_pylist()
        if row["path"]
        and SAFE_PATH_KEY.fullmatch(row["path"])
        and "ENG" in (row["available_languages"] or "").split(",")
    }
    return sorted(paths)


def choose_sample(paths: list[str], k: int, seed: int, year: int) -> list[str]:
    """Seeded shuffle, then take the first k.

    Same inputs always give the same sample, and a bigger k is always a superset of a smaller one.
    """
    shuffled = list(paths)
    # A repeatable sample of public judgments, not a secret: a seeded generator is what's wanted here.
    random.Random(f"{seed}-{year}").shuffle(shuffled)  # nosec B311
    return shuffled[:k]


def download_subset(
    client: httpx.Client,
    data_dir: Path,
    years: list[int],
    per_year: int,
    seed: int = 42,
    progress: Callable[[str], None] = print,
) -> Manifest:
    raw_dir = data_dir / RAW_DIR
    manifest_file = raw_dir / MANIFEST_NAME
    manifest = Manifest.load(manifest_file)
    if manifest.selected and manifest.seed != seed:
        raise ValueError(f"Existing subset used seed {manifest.seed}; delete {manifest_file} to start a new one")
    manifest.seed = seed

    for year in years:
        meta = manifest.metadata.get(year)
        if meta is None or not (raw_dir / meta.key).exists():
            progress(f"[{year}] downloading metadata ...")
            meta = download_file(client, metadata_key(year), raw_dir, max_bytes=MAX_METADATA_BYTES, expect_pdf=False)
            manifest.metadata[year] = meta
            manifest.save(manifest_file)

        candidates = eligible_paths(raw_dir / meta.key)
        sample = choose_sample(candidates, per_year, seed, year)
        manifest.selected[year] = sorted(set(manifest.selected.get(year, [])) | set(sample))
        progress(f"[{year}] {len(candidates)} English judgments available, {len(sample)} selected")

        for n, path in enumerate(sample, start=1):
            known = manifest.pdfs.get(path)
            if known and (raw_dir / known.key).exists():
                continue
            try:
                manifest.pdfs[path] = download_file(
                    client, pdf_key(year, path), raw_dir, max_bytes=MAX_PDF_BYTES, expect_pdf=True
                )
                manifest.failed.pop(path, None)
            except DownloadError as exc:
                manifest.failed[path] = str(exc)
                logger.warning("PDF %s failed: %s", path, exc)
            if n % 10 == 0 or n == len(sample):
                progress(f"[{year}] PDFs {n}/{len(sample)}")
                manifest.save(manifest_file)

    manifest.save(manifest_file)
    return manifest
