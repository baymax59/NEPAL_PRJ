"""Find the statutory provisions cited in every processed document.

Run from the backend folder:
    uv run python -m scripts.extract_provisions
New documents get this automatically in scripts.process_documents. Run this script after
changing app/explain/provisions.py: it reads stored page text, so it needs no PDFs and
doesn't touch chunks or embeddings.
"""

import time

from sqlalchemy import func, select

from app.db.models import DocumentProvision
from app.db.session import SessionLocal
from app.explain.indexing import index_all_provisions


def main() -> None:
    started = time.perf_counter()
    with SessionLocal() as session:
        documents, provisions = index_all_provisions(session)
        top = session.execute(
            select(DocumentProvision.label, func.count(func.distinct(DocumentProvision.case_id)).label("cases"))
            .group_by(DocumentProvision.label)
            .order_by(func.count(func.distinct(DocumentProvision.case_id)).desc(), DocumentProvision.label)
            .limit(10)
        ).all()

    print(f"\n{provisions} distinct provisions across {documents} documents ({time.perf_counter() - started:.1f}s)")
    print("Most widely cited:")
    for label, cases in top:
        print(f"  {cases:3d} cases  {label}")


if __name__ == "__main__":
    main()
