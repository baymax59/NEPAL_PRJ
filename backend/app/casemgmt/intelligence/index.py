"""Case Intelligence's text index inside cases: each content read once, keyed by its SHA-256.

- An exhibit's bytes (PDF, Word, text files) go through the same extract -> clean -> chunk -> embed steps as
  the knowledge base, so passages of a case and of past judgments are comparable. Its hash is checked first
  (an integrity check with the reason "indexing"): a file that doesn't match its hash is never read.
- A note's, analysis's or summary's content (JSON) is turned into plain text and indexed the same way.
- The result is shared: the same file in ten clones, or the same note in a clone and its source, is read once.
- Texts and pages never change. A passage's meaning vector can be added later (the model wasn't loaded) or
  recomputed by a newer model.

When it runs: an uploaded exhibit is indexed right after the upload is answered (index_in_background). Every
Case Intelligence request first indexes what the case still lacks (ensure_indexed): notes always (they are
small), documents within a time budget. What isn't ready yet is reported in the coverage, never guessed.
"""

import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.casemgmt import evidence
from app.casemgmt.enums import IntegrityResult, IntegrityTrigger, TextSourceKind, TextStatus
from app.casemgmt.intelligence.scope import Source
from app.casemgmt.models import ArtifactVersion, EvidenceObject, ObjectChunk, ObjectPage, ObjectText
from app.casemgmt.storage import EvidenceStore
from app.documents.chunk import chunk_pages
from app.documents.clean import clean_pages
from app.documents.extract import DOCX_MIME, ExtractionError, extract_known
from app.embeddings.model import Embedder
from app.explain.indexing import count_provisions

logger = logging.getLogger(__name__)

DOCUMENT_MIME = {"application/pdf", DOCX_MIME}
TEXT_MIME = {"text/plain", "text/csv", "application/json", "message/rfc822", "text/markdown", "application/xml"}
MAX_READ_BYTES = 25 * 1024 * 1024
MIN_PAGE_CHARS = 30  # less text than this on a page with images: probably scanned (as for the knowledge base)
ARTIFACT_EXTRACTOR = "artifact content (JSON as text)"
EMBED_BATCH = 64
# Identifiers inside a note's content say nothing a search or a comparison could use.
_SKIPPED_KEYS = {"case_id", "item_id", "version_id", "artifact_id", "evidence_id", "sha256", "based_on_entry", "as_of_entry",
                 "derived_from", "source_hash", "capture_sha256", "contract_version", "as_received"}


# ---------------------------------------------------------------- what can be read


def unreadable_reason(source: Source) -> str | None:
    """Why an entry's text can't be read (None: it can)."""
    if source.kind == TextSourceKind.ARTIFACT:
        return None
    if source.active_content:
        return "active content (a program, script or web page) is never opened by the application"
    if (source.size_bytes or 0) > MAX_READ_BYTES:
        return f"larger than {MAX_READ_BYTES // (1024 * 1024)} MB"
    if source.mime_type in DOCUMENT_MIME or source.mime_type in TEXT_MIME:
        return None
    kind = (source.category or "this kind of").replace("_", " ")
    return f"no text to read in a {kind} file (text recognition in images, audio and video isn't available yet)"


def decode_text(raw: bytes) -> str:
    """The text of a text file: UTF-8 (with or without a BOM), UTF-16 with a BOM, or older Windows exports."""
    encodings = ("utf-16",) if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252")
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _label(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def artifact_text(content: Any) -> str:
    """A note's content as plain text: its text fields as written, other fields as 'Label: value' lines.

    Depends on the content only (not on the artifact's title or type): equal content gets the same text and index.
    """
    lines: list[str] = []

    def walk(value: Any, label: str | None) -> None:
        if isinstance(value, str):
            value = value.strip()
            if value:
                lines.append(f"{label}: {value}" if label else value)
        elif isinstance(value, bool) or value is None:
            return
        elif isinstance(value, int | float):
            if label:
                lines.append(f"{label}: {value}")
        elif isinstance(value, list):
            for item in value:
                walk(item, label)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in _SKIPPED_KEYS:
                    continue
                walk(item, None if key in ("text", "body") else _label(str(key)))

    walk(content, None)
    return "\n".join(lines)


# ---------------------------------------------------------------- reading and storing


@dataclass
class _Read:
    status: TextStatus
    pages: list[tuple[int | None, str, bool]] = field(default_factory=list)  # (page number, cleaned text, looks scanned)
    extractor: str | None = None
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)


def _read_document(path, mime: str) -> _Read:
    if mime in DOCUMENT_MIME:
        extracted = extract_known(path, mime)
        raw_pages = [(p.number, p.text, p.has_images) for p in extracted.pages]
        extractor = extracted.extractor
        page_count = len(extracted.pages) if extracted.has_page_numbers else None
    else:
        raw_pages = [(None, decode_text(path.read_bytes()), False)]
        extractor, page_count = "plain-text", None
    cleaned = clean_pages([text for _, text, _ in raw_pages])
    pages = [(number, text, len(text) < MIN_PAGE_CHARS and images) for (number, _, images), text in zip(raw_pages, cleaned, strict=True)]
    scanned = [number for number, _, looks_scanned in pages if looks_scanned and number is not None]
    warnings = [f"Pages {', '.join(map(str, scanned))} look scanned; their text is missing (no text recognition yet)"] if scanned else []
    has_text = any(text for _, text, _ in pages)
    return _Read(TextStatus.INDEXED if has_text else TextStatus.NO_TEXT, pages, extractor, page_count, warnings)


def _store(session: Session, kind: TextSourceKind, sha256: str, mime: str | None, read: _Read,
           embedder: Embedder | None) -> ObjectText:
    """Record a content's text once. If another request recorded it meanwhile, that record is kept and returned."""
    texts = [(number, text) for number, text, _ in read.pages if text]
    chunks = chunk_pages(texts) if read.status == TextStatus.INDEXED else []
    vectors = embedder.embed_passages([c.text for c in chunks]) if embedder is not None and chunks else []
    provisions = [{"key": p.key, "label": p.label, "act": p.act, "kind": p.kind, "number": p.number, "mentions": count,
                   "pages": pages} for p, count, pages in count_provisions(texts)]
    created = session.scalar(
        insert(ObjectText).values(
            source_kind=kind.value, sha256=sha256, status=read.status.value, mime_type=mime, extractor=read.extractor,
            page_count=read.page_count, char_count=sum(len(t) for _, t in texts), chunk_count=len(chunks),
            scanned_pages=[n for n, _, scanned in read.pages if scanned and n is not None], provisions=provisions,
            warnings=read.warnings,
        ).on_conflict_do_nothing(index_elements=["source_kind", "sha256"]).returning(ObjectText.sha256)
    )
    if created is not None:
        if read.pages:
            session.execute(insert(ObjectPage), [
                {"source_kind": kind.value, "sha256": sha256, "page_index": i, "page_number": number, "text": text,
                 "needs_ocr": scanned} for i, (number, text, scanned) in enumerate(read.pages)])
        if chunks:
            session.execute(insert(ObjectChunk), [
                {"source_kind": kind.value, "sha256": sha256, "chunk_index": c.index, "page_start": c.page_start,
                 "page_end": c.page_end, "text": c.text, "word_count": c.word_count,
                 "embedding": vectors[i] if vectors else None, "embedding_model": embedder.model_name if vectors else None}
                for i, c in enumerate(chunks)])
        session.flush()
    return session.get(ObjectText, (kind.value, sha256))


def index_evidence(session: Session, store: EvidenceStore, obj: EvidenceObject, embedder: Embedder | None,
                   item_id: uuid.UUID | None = None) -> ObjectText | None:
    """Read an exhibit's text once. None (and nothing read) when the stored file doesn't match its hash."""
    existing = session.get(ObjectText, (TextSourceKind.EVIDENCE.value, obj.sha256))
    if existing is not None:
        return existing
    check = evidence.check_object(session, store, obj, actor=None, trigger=IntegrityTrigger.INDEXING, item_id=item_id)
    if check.result != IntegrityResult.MATCH:
        logger.warning("Evidence object %s failed its integrity check (%s); its text was not read", obj.sha256[:12], check.result)
        return None
    try:
        read = _read_document(store.local_path(obj.storage_key), obj.mime_type)
    except ExtractionError as exc:
        read = _Read(TextStatus.UNREADABLE, warnings=[str(exc)])
    return _store(session, TextSourceKind.EVIDENCE, obj.sha256, obj.mime_type, read, embedder)


def index_artifact(session: Session, version: ArtifactVersion, embedder: Embedder | None) -> ObjectText:
    existing = session.get(ObjectText, (TextSourceKind.ARTIFACT.value, version.content_sha256))
    if existing is not None:
        return existing
    text = artifact_text(version.content)
    read = _Read(TextStatus.INDEXED if text else TextStatus.NO_TEXT, [(None, text, False)] if text else [], ARTIFACT_EXTRACTOR)
    return _store(session, TextSourceKind.ARTIFACT, version.content_sha256, "application/json", read, embedder)


def _keys_condition(keys: Iterable[tuple[str, str]]):
    return tuple_(ObjectChunk.source_kind, ObjectChunk.sha256).in_(list(keys))


def embed_missing(session: Session, keys: set[tuple[str, str]], embedder: Embedder | None, limit: int) -> int:
    """Add meaning vectors (of the current model) to passages of these contents that lack them. Returns how many still lack one."""
    if embedder is None or not keys:
        return 0
    needs = or_(ObjectChunk.embedding.is_(None), ObjectChunk.embedding_model != embedder.model_name)
    rows = session.execute(select(ObjectChunk.id, ObjectChunk.text).where(_keys_condition(keys), needs)
                           .order_by(ObjectChunk.id).limit(limit)).all()
    for start in range(0, len(rows), EMBED_BATCH):
        batch = rows[start:start + EMBED_BATCH]
        vectors = embedder.embed_passages([r.text for r in batch])
        session.execute(update(ObjectChunk), [{"id": r.id, "embedding": v, "embedding_model": embedder.model_name}
                                              for r, v in zip(batch, vectors, strict=True)])
    session.flush()
    return session.scalar(select(func.count()).select_from(ObjectChunk).where(_keys_condition(keys), needs)) or 0


# ---------------------------------------------------------------- coverage: what is ready for a case


@dataclass
class Coverage:
    documents: int = 0  # exhibits in the case the user may see
    readable: int = 0  # of which Case Intelligence can read the text
    indexed: int = 0  # read, with text
    pending: list[str] = field(default_factory=list)  # readable, not read yet
    no_text: list[str] = field(default_factory=list)  # read, no text found (e.g. scanned)
    unreadable: list[dict] = field(default_factory=list)  # {display_id, reason}: damaged, password-protected, failed its check
    not_readable: list[dict] = field(default_factory=list)  # {display_id, reason}: images, audio, programs...
    notes: int = 0  # notes, analyses, summaries...
    notes_indexed: int = 0
    passages: int = 0
    passages_without_meaning: int = 0  # no meaning vector from the current model yet: found by words only
    embedding_model: str | None = None

    @property
    def complete(self) -> bool:
        return not self.pending and self.notes_indexed == self.notes and not self.passages_without_meaning

    def as_dict(self) -> dict:
        return {**{k: getattr(self, k) for k in self.__dataclass_fields__}, "complete": self.complete}


def texts_for(session: Session, keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], ObjectText]:
    keys = list(set(keys))
    if not keys:
        return {}
    rows = session.scalars(select(ObjectText).where(tuple_(ObjectText.source_kind, ObjectText.sha256).in_(keys)))
    return {(t.source_kind, t.sha256): t for t in rows}


def coverage(session: Session, sources: list[Source], embedder: Embedder | None, failed: dict[str, str] | None = None) -> Coverage:
    texts = texts_for(session, (s.key for s in sources))
    result = Coverage(embedding_model=embedder.model_name if embedder else None)
    for source in sources:
        text = texts.get(source.key)
        if source.kind == TextSourceKind.ARTIFACT:
            result.notes += 1
            result.notes_indexed += text is not None
            continue
        result.documents += 1
        if (reason := unreadable_reason(source)) is not None:
            result.not_readable.append({"display_id": source.display_id, "reason": reason})
            continue
        result.readable += 1
        if text is None:
            if failed and source.sha256 in failed:
                result.unreadable.append({"display_id": source.display_id, "reason": failed[source.sha256]})
            else:
                result.pending.append(source.display_id)
        elif text.status == TextStatus.INDEXED:
            result.indexed += 1
        elif text.status == TextStatus.NO_TEXT:
            result.no_text.append(source.display_id)
        else:
            result.unreadable.append({"display_id": source.display_id, "reason": "; ".join(text.warnings) or "could not be read"})
    keys = {k for k, t in texts.items() if t.status == TextStatus.INDEXED}
    if keys:
        result.passages = session.scalar(select(func.count()).select_from(ObjectChunk).where(_keys_condition(keys))) or 0
        if embedder is None:
            result.passages_without_meaning = result.passages
        else:
            result.passages_without_meaning = session.scalar(select(func.count()).select_from(ObjectChunk).where(
                _keys_condition(keys), or_(ObjectChunk.embedding.is_(None), ObjectChunk.embedding_model != embedder.model_name))) or 0
    return result


def ensure_indexed(session: Session, store: EvidenceStore, embedder: Embedder | None, sources: list[Source], *,
                   evidence_seconds: float, artifact_limit: int = 500, embed_limit: int = 2000) -> Coverage:
    """Index what these sources still lack (notes first, then documents while time allows), then report coverage."""
    failed = prepare(session, store, embedder, sources, evidence_seconds=evidence_seconds, artifact_limit=artifact_limit,
                     embed_limit=embed_limit)
    return coverage(session, sources, embedder, failed)


def prepare(session: Session, store: EvidenceStore, embedder: Embedder | None, sources: list[Source], *,
            evidence_seconds: float, artifact_limit: int = 500, embed_limit: int = 2000) -> dict[str, str]:
    """Index what these sources still lack. Returns the exhibits that couldn't be read now (sha256 -> why)."""
    texts = texts_for(session, (s.key for s in sources))
    # Always in hash order: two requests indexing the same contents then wait for each other instead of deadlocking.
    missing_artifacts = sorted({s.version_id for s in sources if s.kind == TextSourceKind.ARTIFACT and s.key not in texts})
    for version in session.scalars(select(ArtifactVersion).where(ArtifactVersion.id.in_(missing_artifacts))
                                   .order_by(ArtifactVersion.content_sha256, ArtifactVersion.id).limit(artifact_limit)):
        index_artifact(session, version, embedder)

    failed: dict[str, str] = {}
    deadline = time.monotonic() + evidence_seconds
    by_sha: dict[str, Source] = {}
    for source in sources:
        if source.kind == TextSourceKind.EVIDENCE and source.key not in texts and unreadable_reason(source) is None:
            by_sha.setdefault(source.sha256, source)
    for sha, source in sorted(by_sha.items()):
        if time.monotonic() >= deadline:
            break
        obj = session.get(EvidenceObject, sha)
        if obj is not None and index_evidence(session, store, obj, embedder, item_id=source.item_id) is None:
            failed[sha] = "the stored file is no longer the file that was added, so its text was not read (see Evidence integrity)"

    embed_missing(session, {s.key for s in sources}, embedder, embed_limit)
    return failed


def index_in_background(sessions: Callable[[], Any], store: EvidenceStore, embedder: Embedder | None, sha256: str,
                        item_id: uuid.UUID | None = None) -> None:
    """Index one uploaded exhibit after its upload was answered (FastAPI background task). Never raises:
    whatever doesn't get indexed here is indexed by the next Case Intelligence request that needs it."""
    try:
        with sessions() as session:
            obj = session.get(EvidenceObject, sha256)
            if obj is None or (obj.mime_type not in DOCUMENT_MIME and obj.mime_type not in TEXT_MIME) or obj.size_bytes > MAX_READ_BYTES:
                return
            index_evidence(session, store, obj, embedder, item_id=item_id)
            session.commit()
    except Exception:
        logger.exception("Indexing evidence object %s for Case Intelligence failed; it will be retried when needed", sha256[:12])


def keys_by_source(sources: list[Source]) -> dict[tuple[str, str], list[Source]]:
    """Each index key and the sources that share it (the same file can be two exhibits)."""
    found: dict[tuple[str, str], list[Source]] = defaultdict(list)
    for source in sources:
        found[source.key].append(source)
    return found
