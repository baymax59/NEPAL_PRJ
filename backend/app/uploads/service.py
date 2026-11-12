"""Accept a new case document from a user, safely.

- Only PDF, Word (.docx) and plain text, checked by content as well as name, up to max_upload_mb.
- The user's filename is never used as a path: files are stored as data/uploads/<random id>.<ext>.
- A file that can't be read, or has no text, is deleted straight away and rejected.
- Text goes through the same extract → clean → chunk steps as the historical cases, so
  passages are comparable. Passages are embedded without the query instruction (Step 6).
"""

import hashlib
import re
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.db.models import Upload, UploadChunk
from app.documents.chunk import chunk_pages
from app.documents.clean import clean_pages
from app.documents.extract import ExtractionError, extract
from app.embeddings.model import Embedder
from app.explain.indexing import count_provisions
from app.similar.service import MAX_QUERY_PASSAGES, sample_evenly

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt"}
UPLOADS_DIR = "uploads"  # inside data_dir


class UploadRejected(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def display_name(filename: str | None) -> str:
    """The filename for display only: no folders, no control characters, limited length."""
    name = re.split(r"[\\/]", filename or "")[-1]
    name = "".join(ch for ch in name if ch.isprintable()).strip()
    return name[:200] or "upload"


def save_upload(
    session: Session,
    data_dir: Path,
    filename: str | None,
    stream: BinaryIO,
    *,
    max_bytes: int,
    embedder: Embedder | None,
    owner_id: str | None = None,
) -> Upload:
    suffix = Path(display_name(filename)).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadRejected(415, "Only PDF, Word (.docx) and plain text (.txt) files are accepted")

    upload_id = uuid.uuid4()
    relative_path = Path(UPLOADS_DIR) / f"{upload_id}{suffix}"
    destination = data_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("wb") as out:
            while block := stream.read(1024 * 1024):
                size += len(block)
                if size > max_bytes:
                    raise UploadRejected(413, f"File is larger than {max_bytes // (1024 * 1024)} MB")
                digest.update(block)
                out.write(block)
        if size == 0:
            raise UploadRejected(422, "The file is empty")
        upload = _process(destination, upload_id, relative_path, filename, size, digest.hexdigest(), embedder)
        upload.owner_id = owner_id
        session.add(upload)
        session.commit()
    except Exception:
        destination.unlink(missing_ok=True)  # never keep a file that wasn't accepted and recorded
        raise
    return upload


def _process(path, upload_id, relative_path, filename, size, sha256, embedder) -> Upload:
    try:
        extracted = extract(path)
    except ExtractionError as exc:
        raise UploadRejected(422, str(exc)) from exc

    cleaned = clean_pages([page.text for page in extracted.pages])
    pages = [(page.number, text) for page, text in zip(extracted.pages, cleaned, strict=True)]
    chunks = chunk_pages([(number, text) for number, text in pages if text])
    if not chunks:
        raise UploadRejected(
            422, "No text could be found in the file. Scanned documents need OCR, which is not supported yet."
        )

    warnings = []
    # Only the passages used for comparison are embedded (long documents are sampled), which
    # keeps uploads quick on a CPU.
    to_embed = {chunk.index for chunk in sample_evenly(chunks, MAX_QUERY_PASSAGES)}
    vectors: dict[int, list[float]] = {}
    if embedder is not None:
        selected = [chunk for chunk in chunks if chunk.index in to_embed]
        vectors = dict(zip((c.index for c in selected), embedder.embed_passages([c.text for c in selected]), strict=True))
    else:
        warnings.append("Embedding model not loaded: similarity will use shared provisions only.")
    if len(chunks) > MAX_QUERY_PASSAGES:
        warnings.append(f"Long document: {MAX_QUERY_PASSAGES} of its {len(chunks)} passages, spread evenly, are used for comparison.")

    upload = Upload(
        id=upload_id,
        original_filename=display_name(filename),
        stored_path=relative_path.as_posix(),
        sha256=sha256,
        mime_type=extracted.mime_type,
        size_bytes=size,
        page_count=len(extracted.pages) if extracted.has_page_numbers else None,
        provisions=[
            {"key": p.key, "label": p.label, "mentions": count, "pages": cited_pages}
            for p, count, cited_pages in count_provisions(pages)
        ],
        warnings=warnings,
    )
    upload.chunks = [
        UploadChunk(
            chunk_index=chunk.index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            text=chunk.text,
            word_count=chunk.word_count,
            embedding=vectors.get(chunk.index),
            embedding_model=embedder.model_name if chunk.index in vectors else None,
        )
        for chunk in chunks
    ]
    return upload


def delete_upload(session: Session, data_dir: Path, upload: Upload) -> None:
    """Remove the stored file and every derived row (passages, embeddings)."""
    (data_dir / upload.stored_path).unlink(missing_ok=True)
    session.delete(upload)
    session.commit()
