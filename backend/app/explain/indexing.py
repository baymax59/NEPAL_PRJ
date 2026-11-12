"""Store the provisions each document cites, with mention counts and pages."""

from collections.abc import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import ExtractionStatus
from app.db.models import CaseDocument, DocumentPage, DocumentProvision
from app.explain.provisions import Provision, extract_provisions


def count_provisions(pages: list[tuple[int | None, str]]) -> list[tuple[Provision, int, list[int]]]:
    """(provision, mention count, pages) for every provision cited in `pages`, most-mentioned first."""
    found: dict[str, tuple[Provision, int, set[int]]] = {}
    for page_number, text in pages:
        for provision in extract_provisions(text):
            _, count, page_set = found.get(provision.key, (provision, 0, set()))
            if page_number is not None:
                page_set.add(page_number)
            found[provision.key] = (provision, count + 1, page_set)
    ordered = sorted(found.values(), key=lambda item: (-item[1], item[0].label))
    return [(provision, count, sorted(page_set)) for provision, count, page_set in ordered]


def store_provisions(session: Session, document: CaseDocument, pages: list[tuple[int | None, str]]) -> int:
    """Replace the document's provisions with those found in `pages` (page number, text)."""
    session.execute(delete(DocumentProvision).where(DocumentProvision.document_id == document.id))
    found = count_provisions(pages)
    session.add_all(
        DocumentProvision(
            document_id=document.id,
            case_id=document.case_id,
            provision_key=provision.key,
            label=provision.label,
            act=provision.act,
            kind=provision.kind,
            number=provision.number,
            mention_count=count,
            pages=pages_cited,
        )
        for provision, count, pages_cited in found
    )
    return len(found)


def index_all_provisions(session: Session, progress: Callable[[str], None] = print) -> tuple[int, int]:
    """(Re)build provisions for every extracted document from its stored page text."""
    documents = session.scalars(
        select(CaseDocument).where(CaseDocument.extraction_status == ExtractionStatus.EXTRACTED.value)
    ).all()
    total = 0
    for n, document in enumerate(documents, start=1):
        pages = session.execute(
            select(DocumentPage.page_number, DocumentPage.text)
            .where(DocumentPage.document_id == document.id)
            .order_by(DocumentPage.page_number)
        ).all()
        total += store_provisions(session, document, [(p.page_number, p.text) for p in pages])
        session.commit()
        if n % 25 == 0 or n == len(documents):
            progress(f"documents {n}/{len(documents)}")
    return len(documents), total
