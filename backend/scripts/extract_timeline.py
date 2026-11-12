"""Build case timelines and court mentions for every processed document.

Run from the backend folder:
    uv run python -m scripts.extract_timeline
New documents get this automatically in scripts.process_documents. Run it again after changing
app/extraction/: it reads stored page text, so it needs no PDFs and doesn't touch embeddings.
"""

import time

from sqlalchemy import func, select

from app.db.models import CaseEntity, CaseEvent
from app.db.session import SessionLocal
from app.extraction.indexing import rebuild_all


def main() -> None:
    started = time.perf_counter()
    with SessionLocal() as session:
        documents, events = rebuild_all(session)
        by_type = session.execute(select(CaseEvent.event_type, func.count()).group_by(CaseEvent.event_type)).all()
        courts = session.execute(
            select(CaseEntity.value, func.count(func.distinct(CaseEntity.case_id)))
            .where(CaseEntity.kind == "court")
            .group_by(CaseEntity.value)
            .order_by(func.count(func.distinct(CaseEntity.case_id)).desc(), CaseEntity.value)
            .limit(8)
        ).all()

    print(f"\n{events} timeline events from {documents} documents ({time.perf_counter() - started:.1f}s)")
    print("By type: " + ", ".join(f"{kind} {n}" for kind, n in sorted(by_type)))
    print("Courts named in most cases:")
    for name, cases in courts:
        print(f"  {cases:3d} cases  {name}")


if __name__ == "__main__":
    main()
