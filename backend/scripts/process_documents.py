"""Extract text from imported documents and split it into searchable chunks.

Run from the backend folder (after scripts.sc_import):
    uv run python -m scripts.process_documents
    uv run python -m scripts.process_documents --reprocess    # redo every document
"""

import argparse
import time

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import DocumentChunk, DocumentPage
from app.db.session import SessionLocal
from app.documents.processing import process_documents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reprocess", action="store_true", help="process all documents again, not just pending")
    parser.add_argument("--limit", type=int, help="process at most this many documents")
    args = parser.parse_args()

    started = time.perf_counter()
    with SessionLocal() as session:
        stats = process_documents(session, get_settings().data_dir, reprocess=args.reprocess, limit=args.limit)
        pages = session.scalar(select(func.count()).select_from(DocumentPage))
        chunks, avg_words = session.execute(
            select(func.count(), func.avg(DocumentChunk.word_count)).select_from(DocumentChunk)
        ).one()

    print()
    print("Documents: " + " | ".join(f"{status} {n}" for status, n in stats.items()))
    print(f"In database: {pages} pages, {chunks} chunks (average {avg_words or 0:.0f} words)")
    print(f"Took {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
