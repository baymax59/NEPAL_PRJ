"""Store the timeline events and court mentions found in a document."""

from collections import defaultdict
from collections.abc import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import EventSource, EventType, ExtractionStatus
from app.db.models import CaseDocument, CaseEntity, CaseEvent, DocumentPage
from app.extraction.courts import find_courts
from app.extraction.timeline import events_from_pages, judgment_event


def store_timeline_and_entities(session: Session, document: CaseDocument, pages: list[tuple[int | None, str]]) -> int:
    """Replace this document's automatic events and court mentions. Manually entered events are kept."""
    case = document.case
    session.execute(
        delete(CaseEvent).where(
            CaseEvent.document_id == document.id, CaseEvent.extraction_method == EventSource.RULE_BASED.value
        )
    )
    session.execute(
        delete(CaseEvent).where(
            CaseEvent.case_id == case.id,
            CaseEvent.event_type == EventType.JUDGMENT.value,
            CaseEvent.extraction_method == EventSource.SOURCE_FIELD.value,
        )
    )
    session.execute(delete(CaseEntity).where(CaseEntity.document_id == document.id))

    decision_date = case.primary_date if case.primary_date_kind == "decision" else None
    events = events_from_pages(pages, decision_date)
    judgment = judgment_event(decision_date, case.outcome, case.court_or_agency)
    for event in ([judgment] if judgment else []) + events:
        session.add(
            CaseEvent(
                case_id=case.id,
                document_id=None if event.event_type == EventType.JUDGMENT else document.id,
                event_type=event.event_type,
                event_date=event.event_date,
                date_text=event.date_text,
                description=event.description,
                page_number=event.page_number,
                source_excerpt=event.source_excerpt,
                extraction_method=event.extraction_method,
            )
        )

    courts: dict[str, tuple[int, set[int]]] = defaultdict(lambda: (0, set()))
    for page_number, text in pages:
        for mention in find_courts(text):
            count, page_set = courts[mention.name]
            if page_number is not None:
                page_set.add(page_number)
            courts[mention.name] = (count + 1, page_set)
    session.add_all(
        CaseEntity(
            document_id=document.id,
            case_id=case.id,
            kind="court",
            value=name,
            mentions=count,
            pages=sorted(page_set),
        )
        for name, (count, page_set) in courts.items()
    )
    session.flush()
    return len(events) + (1 if judgment else 0)


def rebuild_all(session: Session, progress: Callable[[str], None] = print) -> tuple[int, int]:
    """(documents, events): rebuild from stored page text for every extracted document."""
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
        total += store_timeline_and_entities(session, document, [(p.page_number, p.text) for p in pages])
        session.commit()
        if n % 25 == 0 or n == len(documents):
            progress(f"documents {n}/{len(documents)}")
    return len(documents), total
